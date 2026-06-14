from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.batch_expiry import FAR_FUTURE_EXPIRY
from core.models import (
    Category,
    Company,
    Equipment,
    EquipmentSlot,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    StockItem,
    Store,
    SupplyReceivingTask,
    Zone,
)
from core.placement_execution import accept_placement_task, complete_placement_task
from core.tests.placement_scan_helpers import fulfill_placement_scan_requirements
from core.placement_sync import (
    available_batch_qty,
    deduct_from_batches,
    reconcile_planogram,
    sync_stock_item_from_batches,
)

User = get_user_model()


class PlacementStockSyncTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Sync Co")
        self.store = Store.objects.create(name="Sync Store", address="Addr")
        self.zone = Zone.objects.create(name="Hall", store=self.store, color="#ccc")
        self.equipment = Equipment.objects.create(
            name="Shelf",
            zone=self.zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=120,
            height=60,
            rows_count=2,
        )
        self.slot = EquipmentSlot.objects.filter(equipment=self.equipment).first()
        self.slot.width_percent = 100
        self.slot.save(update_fields=["width_percent"])
        self.category = Category.objects.create(name="Apparel")
        self.product = Product.objects.create(
            name="Футболка",
            sku="TSH-SYNC",
            category=self.category,
            price=Decimal("500.00"),
            width=300,
            height=50,
            depth=250,
            weight=200,
            shelf_life_days=None,
        )
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=4,
        )
        self.slot.refresh_from_db()
        self.employee = User.objects.create_user(
            username="sync_emp",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.admin = User.objects.create_user(
            username="sync_admin",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.client = APIClient()

    def test_sync_stock_item_from_batches_ignores_expired(self):
        ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=10,
            expiration_date=date.today() - timedelta(days=1),
            purchase_price="100.00",
        )
        ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=6,
            current_quantity=6,
            expiration_date=FAR_FUTURE_EXPIRY,
            purchase_price="100.00",
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 99})

        synced = sync_stock_item_from_batches(self.product.pk)
        self.assertEqual(synced, 6)
        self.assertEqual(available_batch_qty(self.product.pk), 6)
        stock = StockItem.objects.get(product=self.product)
        self.assertEqual(int(stock.quantity), 6)

    def test_reconcile_skips_task_when_batches_expired_but_stock_positive(self):
        ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=10,
            expiration_date=date.today() - timedelta(days=1),
            purchase_price="100.00",
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 10})
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()

        reconcile_planogram(self.planogram)

        self.assertFalse(
            PlacementTask.objects.filter(
                planogram=self.planogram,
                status__in=(
                    PlacementTask.Status.CREATED,
                    PlacementTask.Status.PENDING,
                    PlacementTask.Status.IN_PROGRESS,
                ),
            ).exists()
        )

    def test_deduct_syncs_stock_item(self):
        batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=8,
            current_quantity=8,
            expiration_date=FAR_FUTURE_EXPIRY,
            purchase_price="100.00",
        )
        sync_stock_item_from_batches(self.product.pk)

        deducted, _ = deduct_from_batches(self.product.pk, 3)
        self.assertEqual(deducted, 3)
        batch.refresh_from_db()
        self.assertEqual(int(batch.current_quantity), 5)
        stock = StockItem.objects.get(product=self.product)
        self.assertEqual(int(stock.quantity), 5)
        self.assertEqual(available_batch_qty(self.product.pk), 5)

    def test_apparel_receiving_and_complete_placement(self):
        self.client.force_authenticate(self.admin)
        order_resp = self.client.post(
            "/api/supply-orders/",
            {
                "status": "ordered",
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": 12,
                        "purchase_price": "200.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(order_resp.status_code, 201)
        order_id = order_resp.data["id"]
        item_id = order_resp.data["items"][0]["id"]
        task_id = SupplyReceivingTask.objects.get(supply_order_id=order_id).pk

        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        complete_recv = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/",
            {"lines": [{"item_id": item_id, "actual_quantity": 12}]},
            format="json",
        )
        self.assertEqual(complete_recv.status_code, 200)

        batch = ProductBatch.objects.filter(supply_item_id=item_id).first()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.expiration_date, FAR_FUTURE_EXPIRY)
        stock = StockItem.objects.get(product=self.product)
        self.assertEqual(int(stock.quantity), 12)

        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        reconcile_planogram(self.planogram)

        placement = PlacementTask.objects.filter(
            planogram=self.planogram,
            status=PlacementTask.Status.CREATED,
        ).first()
        self.assertIsNotNone(placement)

        accept_placement_task(placement.pk, self.employee)
        fulfill_placement_scan_requirements(placement, self.employee)
        complete_placement_task(placement.pk, self.employee, None)

        placement.refresh_from_db()
        self.slot.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(placement.status, PlacementTask.Status.COMPLETED)
        self.assertGreater(int(self.slot.current_qty), 0)
        self.assertEqual(int(stock.quantity), 12 - int(placement.quantity))

    def test_complete_placement_updates_existing_no_batch_inventory(self):
        from core.models import Inventory

        ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=10,
            expiration_date=FAR_FUTURE_EXPIRY,
            purchase_price="100.00",
        )
        sync_stock_item_from_batches(self.product.pk)
        Inventory.objects.create(
            store=self.store,
            product=self.product,
            status=Inventory.LocationStatus.WAREHOUSE,
            quantity=10,
        )
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=3,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        fulfill_placement_scan_requirements(task, self.employee)
        complete_placement_task(task.pk, self.employee, None)
        inv = Inventory.objects.get(
            store=self.store,
            product=self.product,
            batch__isnull=True,
        )
        self.assertEqual(inv.status, Inventory.LocationStatus.SHELF)
        self.assertEqual(int(inv.quantity), 3)
