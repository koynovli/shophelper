from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from io import StringIO
from rest_framework.test import APIClient

from core.tests.placement_scan_helpers import product_scan_payload
from core.expiry_writeoff import write_off_expired_shelf_stock
from core.models import (
    Category,
    Equipment,
    EquipmentSlot,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Shelf,
    ShelfWriteOff,
    StockItem,
    Store,
    WriteOffTask,
    Zone,
)

User = get_user_model()


class ExpiryWriteOffTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="W Store", address="A")
        self.zone = Zone.objects.create(name="Hall", store=self.store, color="#fff")
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
        self.shelf, _ = Shelf.objects.get_or_create(
            equipment=self.equipment,
            level=1,
            defaults={"width": 100, "height": 40, "depth": 50},
        )
        self.slot.shelf = self.shelf
        self.slot.max_capacity = 20
        self.slot.save(update_fields=["shelf", "max_capacity"])
        self.category = Category.objects.create(name="Food")
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-W",
            category=self.category,
            price="50.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=10,
        )
        self.expired_batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=0,
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
            defaults={"quantity": 20},
        )
        self.admin = User.objects.create_user(
            username="adm",
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

    def _complete_shelf_write_off_task(self) -> WriteOffTask:
        task = WriteOffTask.objects.get(location=WriteOffTask.Location.SHELF)
        client = APIClient()
        client.force_authenticate(self.employee)
        client.post(f"/api/write-off-tasks/{task.pk}/accept/")
        client.post(
            f"/api/write-off-tasks/{task.pk}/complete/",
            product_scan_payload(self.product),
            format="json",
        )
        return task

    def test_legacy_write_off_creates_shelf_task(self):
        self._completed_placement(self.expired_batch)
        result = write_off_expired_shelf_stock(store_id=self.store.pk)
        self.assertEqual(result.slots_written_off, 1)
        self.assertEqual(result.units_written_off, 5)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)
        self.assertEqual(WriteOffTask.objects.filter(location=WriteOffTask.Location.SHELF).count(), 1)
        self.assertEqual(ShelfWriteOff.objects.count(), 0)

        self._complete_shelf_write_off_task()
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 0)
        self.assertEqual(ShelfWriteOff.objects.count(), 1)
        row = ShelfWriteOff.objects.get()
        self.assertEqual(row.quantity, 5)
        self.assertEqual(row.batch_id, self.expired_batch.pk)

    def test_skip_when_last_batch_fresh(self):
        self._completed_placement(self.fresh_batch)
        write_off_expired_shelf_stock(store_id=self.store.pk)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)
        self.assertEqual(WriteOffTask.objects.count(), 0)
        self.assertEqual(ShelfWriteOff.objects.count(), 0)

    def test_dry_run_no_db_changes(self):
        self._completed_placement(self.expired_batch)
        result = write_off_expired_shelf_stock(store_id=self.store.pk, dry_run=True)
        self.assertEqual(result.slots_written_off, 1)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)
        self.assertEqual(WriteOffTask.objects.count(), 0)
        self.assertEqual(ShelfWriteOff.objects.count(), 0)

    def test_management_command_dry_run(self):
        self._completed_placement(self.expired_batch)
        out = StringIO()
        call_command("scan_write_off_tasks", "--dry-run", stdout=out)
        self.assertIn("dry-run", out.getvalue().lower())
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)

    def test_api_scan_write_off_tasks(self):
        self._completed_placement(self.expired_batch)
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.post("/api/inventory/scan-write-off-tasks/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["shelf_tasks"], 1)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)
        self.assertTrue(
            WriteOffTask.objects.filter(location=WriteOffTask.Location.SHELF).exists()
        )
