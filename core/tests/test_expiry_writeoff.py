from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from io import StringIO
from rest_framework.test import APIClient

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
            type=Equipment.EquipmentType.SHELVING,
            pos_x=0,
            pos_y=0,
            width=100,
            height=50,
            rows_count=1,
        )
        self.slot = self.equipment.slots.first()
        self.shelf = Shelf.objects.create(
            equipment=self.equipment,
            level=1,
            width=100,
            height=40,
            depth=50,
        )
        self.slot.shelf = self.shelf
        self.slot.max_capacity = 20
        self.slot.current_qty = 5
        self.slot.save()
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
            expiration_date=date.today() - timedelta(days=1),
            purchase_price="40.00",
        )
        self.fresh_batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=20,
            current_quantity=20,
            expiration_date=date.today() + timedelta(days=10),
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

    def test_write_off_expired_placement_batch(self):
        self._completed_placement(self.expired_batch)
        result = write_off_expired_shelf_stock(store_id=self.store.pk)
        self.assertEqual(result.slots_written_off, 1)
        self.assertEqual(result.units_written_off, 5)
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
        self.assertEqual(ShelfWriteOff.objects.count(), 0)

    def test_dry_run_no_db_changes(self):
        self._completed_placement(self.expired_batch)
        result = write_off_expired_shelf_stock(store_id=self.store.pk, dry_run=True)
        self.assertEqual(result.slots_written_off, 1)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)
        self.assertEqual(ShelfWriteOff.objects.count(), 0)

    def test_management_command_dry_run(self):
        self._completed_placement(self.expired_batch)
        out = StringIO()
        call_command("write_off_expired_shelf", "--dry-run", stdout=out)
        self.assertIn("dry-run", out.getvalue())
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 5)

    def test_api_write_off_expired(self):
        self._completed_placement(self.expired_batch)
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.post("/api/inventory/write-off-expired/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["units_written_off"], 5)
        self.slot.refresh_from_db()
        self.assertEqual(int(self.slot.current_qty), 0)
