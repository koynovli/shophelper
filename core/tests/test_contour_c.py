from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    EquipmentSlot,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StaffTask,
    StockItem,
    Store,
    Zone,
)
from core.spatial_engine import refresh_slot_max_capacity

User = get_user_model()


@override_settings(MEDIA_ROOT="/tmp/shophelper_test_media")
class ContourCTaskTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Test Store", address="Addr")
        self.zone = Zone.objects.create(name="Main", store=self.store, color="#fff")
        self.equipment = Equipment.objects.create(
            name="Rack A",
            zone=self.zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=100,
            height=50,
            rows_count=2,
        )
        self.slot = self.equipment.slots.first()
        if self.slot is None:
            self.slot = EquipmentSlot.objects.create(
                equipment=self.equipment,
                row_index=0,
                col_index=0,
            )
        self.category = Category.objects.create(name="Dairy")
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-1",
            category=self.category,
            price="50.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=20,
            current_quantity=20,
            expiration_date=date.today() + timedelta(days=10),
            purchase_price="40.00",
        )
        StockItem.objects.update_or_create(
            product=self.product,
            defaults={"quantity": 10},
        )
        Shelf.objects.get_or_create(
            equipment=self.equipment,
            level=1,
            defaults={"width": 100, "height": 40, "depth": 50},
        )
        self.slot.shelf = Shelf.objects.filter(equipment=self.equipment, level=1).first()
        self.slot.current_qty = 0
        self.slot.save(update_fields=["shelf", "current_qty"])
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=5,
        )
        refresh_slot_max_capacity(self.slot, self.product)
        self.placement = PlacementTask.objects.filter(
            planogram=self.planogram,
            status__in=(PlacementTask.Status.CREATED, PlacementTask.Status.PENDING),
        ).first()
        if self.placement is None:
            self.placement = PlacementTask.objects.create(
                planogram=self.planogram,
                product=self.product,
                equipment=self.equipment,
                quantity=3,
                batch=self.batch,
                status=PlacementTask.Status.CREATED,
            )
        else:
            self.placement.batch = self.batch
            self.placement.quantity = 3
            self.placement.save(update_fields=["batch", "quantity"])
        self.employee = User.objects.create_user(
            username="emp1",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.admin = User.objects.create_user(
            username="admin1",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.client = APIClient()

    def test_task_pool_returns_both_types(self):
        StaffTask.objects.create(
            title="Clean zone",
            created_by=self.admin,
            zone=self.zone,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/task-pool/")
        self.assertEqual(resp.status_code, 200)
        types = {item["task_type"] for item in resp.data}
        self.assertIn("placement", types)
        self.assertIn("staff", types)

    def test_task_pool_placement_includes_slot_info(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/task-pool/")
        self.assertEqual(resp.status_code, 200)
        placement = next(item for item in resp.data if item["task_type"] == "placement")
        self.assertIsNotNone(placement.get("slot_info"))
        self.assertEqual(placement["slot_info"]["id"], self.slot.pk)

    def test_placement_accept_and_complete_without_qr_or_photo(self):
        self.client.force_authenticate(self.employee)
        accept = self.client.post(f"/api/placement-tasks/{self.placement.pk}/accept/")
        self.assertEqual(accept.status_code, 200)

        done = self.client.post(f"/api/placement-tasks/{self.placement.pk}/complete/")
        self.assertEqual(done.status_code, 200)
        self.placement.refresh_from_db()
        self.assertEqual(self.placement.status, PlacementTask.Status.COMPLETED)
        self.assertFalse(self.placement.photo_url)

    def test_placement_verify_slot_still_works_but_optional(self):
        self.client.force_authenticate(self.employee)
        accept = self.client.post(f"/api/placement-tasks/{self.placement.pk}/accept/")
        self.assertEqual(accept.status_code, 200)

        bad_qr = self.client.post(
            f"/api/placement-tasks/{self.placement.pk}/verify-slot/",
            {"qr_token": "00000000-0000-0000-0000-000000000001"},
            format="json",
        )
        self.assertEqual(bad_qr.status_code, 400)

        ok_qr = self.client.post(
            f"/api/placement-tasks/{self.placement.pk}/verify-slot/",
            {"qr_token": str(self.slot.qr_token)},
            format="json",
        )
        self.assertEqual(ok_qr.status_code, 200)
        self.placement.refresh_from_db()
        self.assertIsNotNone(self.placement.slot_verified_at)

    def test_staff_task_lifecycle(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post(
            "/api/staff-tasks/",
            {
                "title": "Уборка",
                "description": "Помыть пол",
                "zone": self.zone.pk,
                "requires_photo": False,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        task_id = create.data["id"]

        self.client.force_authenticate(self.employee)
        accept = self.client.post(f"/api/staff-tasks/{task_id}/accept/")
        self.assertEqual(accept.status_code, 200)

        msg = self.client.post(
            f"/api/staff-tasks/{task_id}/messages/",
            {"text": "Начинаю уборку"},
            format="json",
        )
        self.assertEqual(msg.status_code, 201)

        done = self.client.post(f"/api/staff-tasks/{task_id}/complete/")
        self.assertEqual(done.status_code, 200)
