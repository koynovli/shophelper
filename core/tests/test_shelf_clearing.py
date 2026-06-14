from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    ShelfClearingTask,
    StockItem,
    Store,
    Zone,
)
from core.tests.placement_scan_helpers import product_scan_payload

User = get_user_model()


class ShelfClearingTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Cat")
        self.admin = User.objects.create_user(
            username="admin",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.employee = User.objects.create_user(
            username="emp",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.client = APIClient()
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-L",
            category=self.category,
            price="50.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.equipment = Equipment.objects.create(
            name="Rack",
            zone=self.zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=2,
        )
        self.slot = self.equipment.slots.first()
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=5,
        )
        self.batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=100,
            current_quantity=50,
            expiration_date=timezone.localdate() + timedelta(days=365),
            purchase_price="100.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 50})
        self.slot.current_qty = 5
        self.slot.save(update_fields=["current_qty"])
        self.placement_task = PlacementTask.objects.filter(
            planogram=self.planogram,
            status=PlacementTask.Status.CREATED,
        ).first()

    def test_create_accept_complete_returns_stock_and_clears_slot(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post(
            "/api/shelf-clearing-tasks/",
            {"slot_id": self.slot.pk},
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        task_id = create.data["id"]

        self.client.force_authenticate(self.employee)
        accept = self.client.post(f"/api/shelf-clearing-tasks/{task_id}/accept/")
        self.assertEqual(accept.status_code, 200)

        complete = self.client.post(
            f"/api/shelf-clearing-tasks/{task_id}/complete/",
            product_scan_payload(self.product),
            format="json",
        )
        self.assertEqual(complete.status_code, 200)

        self.slot.refresh_from_db()
        self.batch.refresh_from_db()
        stock = StockItem.objects.get(product=self.product)

        self.assertEqual(self.slot.current_qty, 0)
        self.assertEqual(self.batch.current_quantity, 55)
        self.assertEqual(stock.quantity, 55)
        self.assertTrue(
            PlacementTask.objects.filter(
                planogram=self.planogram,
                status=PlacementTask.Status.CREATED,
            ).exists()
        )

    def test_after_clearing_layout_patch_allowed(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post(
            "/api/shelf-clearing-tasks/",
            {"slot_id": self.slot.pk},
            format="json",
        )
        task_id = create.data["id"]
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/shelf-clearing-tasks/{task_id}/accept/")
        self.client.post(
            f"/api/shelf-clearing-tasks/{task_id}/complete/",
            product_scan_payload(self.product),
            format="json",
        )

        PlacementTask.objects.filter(
            planogram=self.planogram,
            status=PlacementTask.Status.CREATED,
        ).update(status=PlacementTask.Status.CANCELLED)

        self.client.force_authenticate(self.admin)
        patch = self.client.patch(
            f"/api/floor-equipment/{self.equipment.pk}/",
            {"rows_count": 1},
            format="json",
        )
        self.assertEqual(patch.status_code, 200)

    def test_duplicate_open_clearing_task_rejected(self):
        self.client.force_authenticate(self.admin)
        first = self.client.post(
            "/api/shelf-clearing-tasks/",
            {"slot_id": self.slot.pk},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/shelf-clearing-tasks/",
            {"slot_id": self.slot.pk},
            format="json",
        )
        self.assertEqual(second.status_code, 400)

    def test_planogram_delete_blocked_with_stock(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/planograms/{self.planogram.pk}/")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Planogram.objects.filter(pk=self.planogram.pk).exists())

    def test_clearing_task_in_task_pool(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post(
            "/api/shelf-clearing-tasks/",
            {"slot_id": self.slot.pk},
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        pool = self.client.get("/api/task-pool/", {"task_type": "shelf_clearing"})
        self.assertEqual(pool.status_code, 200)
        types = {item["task_type"] for item in pool.data}
        self.assertIn("shelf_clearing", types)
