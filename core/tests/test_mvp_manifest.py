from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    EquipmentSlot,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    StockItem,
    Store,
    User,
    Zone,
)
from core.placement_execution import complete_placement_task
from core.placement_sync import deduct_from_batches, reconcile_planogram

User = get_user_model()


@override_settings(MEDIA_ROOT="/tmp/shophelper_test_mvp_media")
class MvpManifestTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="MVP Store", address="Addr")
        self.zone = Zone.objects.create(name="Hall", store=self.store, color="#ccc")
        self.equipment = Equipment.objects.create(
            name="Fridge",
            zone=self.zone,
            type=Equipment.EquipmentType.FRIDGE,
            pos_x=0,
            pos_y=0,
            width=100,
            height=80,
            rows_count=2,
        )
        self.slot = self.equipment.slots.order_by("row_index", "col_index").first()
        self.shelf, _ = Shelf.objects.get_or_create(
            equipment=self.equipment,
            level=1,
            defaults={"width": 100, "height": 40, "depth": 50},
        )
        self.slot.shelf = self.shelf
        self.slot.save(update_fields=["shelf"])
        self.category = Category.objects.create(name="Drinks")
        self.product = Product.objects.create(
            name="Water",
            sku="W-1",
            category=self.category,
            price="30.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
            is_stackable=True,
        )
        self.batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=50,
            current_quantity=50,
            expiration_date=date.today() + timedelta(days=30),
            purchase_price="20.00",
        )
        StockItem.objects.update_or_create(
            product=self.product,
            defaults={"quantity": 50},
        )
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=24,
        )
        self.slot.refresh_from_db()
        self.assertGreater(self.slot.max_capacity, 0)

        self.employee = User.objects.create_user(
            username="worker",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.client = APIClient()

    def test_thirty_percent_trigger_creates_created_task(self):
        cap = self.slot.max_capacity
        self.slot.current_qty = max(0, int(cap * 0.2))
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        reconcile_planogram(self.planogram)
        task = PlacementTask.objects.filter(
            planogram=self.planogram,
            status=PlacementTask.Status.CREATED,
        ).first()
        self.assertIsNotNone(task)
        self.assertGreater(task.quantity, 0)
        self.assertEqual(int(self.batch.current_quantity), 50)

    def test_complete_atomic_slot_and_batch(self):
        cap = self.slot.max_capacity
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=4,
            batch=self.batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        from django.utils import timezone

        task.slot_verified_at = timezone.now()
        task.save(update_fields=["slot_verified_at"])
        batch_before = int(self.batch.current_quantity)
        slot_before = int(self.slot.current_qty)
        photo = SimpleUploadedFile("r.jpg", b"jpeg", content_type="image/jpeg")
        complete_placement_task(task.pk, self.employee, photo)
        self.batch.refresh_from_db()
        self.slot.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(task.status, PlacementTask.Status.COMPLETED)
        self.assertEqual(int(self.slot.current_qty), slot_before + 4)
        self.assertEqual(int(self.batch.current_quantity), batch_before - 4)

    def test_deduct_rollback_on_insufficient_batch(self):
        ProductBatch.objects.filter(pk=self.batch.pk).update(current_quantity=1)
        self.batch.refresh_from_db()
        with self.assertRaises(Exception):
            with transaction.atomic():
                deducted, _ = deduct_from_batches(self.product.pk, 5)
                if deducted < 5:
                    raise ValueError("rollback")
        self.batch.refresh_from_db()
        self.assertEqual(int(self.batch.current_quantity), 1)

    def test_adjust_qty_api_triggers_created_task(self):
        cap = self.slot.max_capacity
        self.slot.current_qty = max(1, int(cap * 0.5))
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        admin = User.objects.create_user(
            username="mgr",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        client = APIClient()
        client.force_authenticate(admin)
        resp = client.post(
            f"/api/slots/{self.slot.pk}/adjust-qty/",
            {"delta": -max(1, int(cap * 0.5))},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            PlacementTask.objects.filter(
                planogram=self.planogram,
                status=PlacementTask.Status.CREATED,
            ).exists()
        )

    def test_inventory_sync_updates_slot_qty(self):
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        Inventory.objects.create(
            store=self.store,
            product=self.product,
            shelf=self.shelf,
            status=Inventory.LocationStatus.SHELF,
            quantity=7,
        )
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 7)

    def test_fail_placement_endpoint(self):
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=2,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        self.client.force_authenticate(self.employee)
        resp = self.client.post(
            f"/api/placement-tasks/{task.pk}/fail/",
            {"reason": "Нет на складе"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, PlacementTask.Status.FAILED)
