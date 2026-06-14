from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from io import StringIO
from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    Inventory,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    ShelfWriteOff,
    StockItem,
    Store,
    WarehouseWriteOff,
    WriteOffTask,
    Zone,
)
from core.tests.placement_scan_helpers import product_scan_payload
from core.write_off_service import scan_expired_write_off_tasks

User = get_user_model()


class WriteOffTaskTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="WO Store", address="A")
        self.zone = Zone.objects.create(name="Hall", store=self.store, color="#fff")
        self.category = Category.objects.create(name="Food")
        self.admin = User.objects.create_user(
            username="wo_admin",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.employee = User.objects.create_user(
            username="wo_emp",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.client = APIClient()
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-WO",
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
            height=50,
            rows_count=1,
        )
        self.slot = self.equipment.slots.first()
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=10,
        )
        self.expired_batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=10,
            expiration_date=timezone.localdate() - timedelta(days=2),
            purchase_price="40.00",
        )
        self.fresh_batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=20,
            current_quantity=20,
            expiration_date=timezone.localdate() + timedelta(days=10),
            purchase_price="40.00",
        )
        StockItem.objects.update_or_create(
            product=self.product,
            defaults={"quantity": 30},
        )
        self.slot.current_qty = 5
        self.slot.save(update_fields=["current_qty"])

    def _completed_placement(self, batch: ProductBatch) -> PlacementTask:
        return PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=5,
            batch=batch,
            status=PlacementTask.Status.COMPLETED,
            completed_at=timezone.now(),
        )

    def test_scan_dry_run_finds_warehouse_and_shelf(self):
        self._completed_placement(self.expired_batch)
        result = scan_expired_write_off_tasks(self.store.pk, dry_run=True)
        self.assertEqual(result.warehouse_tasks, 1)
        self.assertEqual(result.shelf_tasks, 1)
        self.assertEqual(result.tasks_total, 2)
        self.assertEqual(WriteOffTask.objects.count(), 0)

    def test_scan_creates_tasks_without_duplicates(self):
        self._completed_placement(self.expired_batch)
        first = scan_expired_write_off_tasks(self.store.pk, dry_run=False)
        self.assertEqual(first.tasks_total, 2)
        self.assertEqual(WriteOffTask.objects.count(), 2)

        second = scan_expired_write_off_tasks(self.store.pk, dry_run=False)
        self.assertEqual(second.tasks_total, 0)
        self.assertEqual(WriteOffTask.objects.count(), 2)

    def test_complete_warehouse_reduces_batch_and_stock(self):
        Inventory.objects.create(
            store=self.store,
            product=self.product,
            batch=self.expired_batch,
            quantity=10,
            status=Inventory.LocationStatus.WAREHOUSE,
        )
        Inventory.objects.create(
            store=self.store,
            product=self.product,
            batch=None,
            quantity=0,
            status=Inventory.LocationStatus.WAREHOUSE,
        )
        task = WriteOffTask.objects.create(
            store=self.store,
            product=self.product,
            batch=self.expired_batch,
            quantity=10,
            location=WriteOffTask.Location.WAREHOUSE,
            trigger=WriteOffTask.Trigger.EXPIRED_AUTO,
            status=WriteOffTask.Status.CREATED,
        )
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/write-off-tasks/{task.pk}/accept/")
        resp = self.client.post(
            f"/api/write-off-tasks/{task.pk}/complete/",
            product_scan_payload(self.product),
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        stock = StockItem.objects.get(product=self.product)
        self.assertFalse(ProductBatch.objects.filter(pk=self.expired_batch.pk).exists())
        self.assertEqual(stock.quantity, 20)
        self.assertEqual(WarehouseWriteOff.objects.count(), 1)

    def test_complete_warehouse_without_photo(self):
        task = WriteOffTask.objects.create(
            store=self.store,
            product=self.product,
            batch=self.fresh_batch,
            quantity=2,
            location=WriteOffTask.Location.WAREHOUSE,
            trigger=WriteOffTask.Trigger.MANUAL,
            reason="Тест",
            status=WriteOffTask.Status.CREATED,
        )
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/write-off-tasks/{task.pk}/accept/")
        resp = self.client.post(
            f"/api/write-off-tasks/{task.pk}/complete/",
            product_scan_payload(self.product),
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], WriteOffTask.Status.COMPLETED)
        self.fresh_batch.refresh_from_db()
        self.assertEqual(self.fresh_batch.current_quantity, 18)

    def test_complete_shelf_clears_slot_and_creates_journal(self):
        placement = self._completed_placement(self.expired_batch)
        task = WriteOffTask.objects.create(
            store=self.store,
            product=self.product,
            batch=self.expired_batch,
            quantity=5,
            location=WriteOffTask.Location.SHELF,
            trigger=WriteOffTask.Trigger.EXPIRED_AUTO,
            slot=self.slot,
            planogram=self.planogram,
            equipment=self.equipment,
            placement_task=placement,
            status=WriteOffTask.Status.CREATED,
        )
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/write-off-tasks/{task.pk}/accept/")
        resp = self.client.post(
            f"/api/write-off-tasks/{task.pk}/complete/",
            product_scan_payload(self.product),
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 0)
        self.assertEqual(ShelfWriteOff.objects.count(), 1)
        cancelled = PlacementTask.objects.filter(
            planogram=self.planogram,
            status=PlacementTask.Status.CANCELLED,
        ).exists()
        self.assertTrue(cancelled)

    def test_manual_warehouse_create_and_complete_fresh_batch(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post(
            "/api/write-off-tasks/",
            {
                "batch_id": self.fresh_batch.pk,
                "quantity": 3,
                "reason": "Бой при транспортировке",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        task_id = create.data["id"]

        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/write-off-tasks/{task_id}/accept/")
        self.client.post(
            f"/api/write-off-tasks/{task_id}/complete/",
            product_scan_payload(self.product),
            format="json",
        )

        self.fresh_batch.refresh_from_db()
        stock = StockItem.objects.get(product=self.product)
        self.assertEqual(self.fresh_batch.current_quantity, 17)
        self.assertEqual(stock.quantity, 17)
        row = WarehouseWriteOff.objects.get()
        self.assertEqual(row.quantity, 3)

    def test_task_pool_includes_write_off(self):
        WriteOffTask.objects.create(
            store=self.store,
            product=self.product,
            batch=self.expired_batch,
            quantity=5,
            location=WriteOffTask.Location.WAREHOUSE,
            trigger=WriteOffTask.Trigger.EXPIRED_AUTO,
            status=WriteOffTask.Status.CREATED,
        )
        self.client.force_authenticate(self.employee)
        resp = self.client.get("/api/task-pool/")
        self.assertEqual(resp.status_code, 200)
        types = {row["task_type"] for row in resp.data}
        self.assertIn("write_off", types)

    def test_api_scan_write_off_tasks(self):
        self._completed_placement(self.expired_batch)
        self.client.force_authenticate(self.admin)
        preview = self.client.post("/api/inventory/scan-write-off-tasks/?dry_run=true")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["tasks_total"], 2)
        self.assertTrue(preview.data["dry_run"])

        create = self.client.post("/api/inventory/scan-write-off-tasks/")
        self.assertEqual(create.status_code, 200)
        self.assertEqual(create.data["tasks_total"], 2)
        self.assertFalse(create.data["dry_run"])

    def test_management_command_scan(self):
        self._completed_placement(self.expired_batch)
        out = StringIO()
        call_command("scan_write_off_tasks", "--dry-run", stdout=out)
        self.assertIn("dry-run", out.getvalue().lower())
        self.assertEqual(WriteOffTask.objects.count(), 0)

        call_command("scan_write_off_tasks", f"--store-id={self.store.pk}", stdout=out)
        self.assertEqual(WriteOffTask.objects.count(), 2)
