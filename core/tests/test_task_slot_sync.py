from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

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
    ShelfClearingTask,
    StockItem,
    Store,
    Zone,
)
from core.placement_execution import complete_placement_task
from core.placement_sync import _merge_open_placement_task_list
from core.shelf_clearing_service import (
    accept_shelf_clearing_task,
    complete_shelf_clearing_task,
    create_shelf_clearing_task,
)
from core.slot_inventory_sync import sync_inventory_from_slot
from core.tests.placement_scan_helpers import fulfill_placement_scan_requirements

User = get_user_model()


class TaskSlotSyncTests(TestCase):
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
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-SYNC",
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
            width=200,
            height=60,
            rows_count=1,
        )
        self.shelf = Shelf.objects.get(equipment=self.equipment, level=1)
        self.slots = list(
            self.equipment.slots.order_by("col_index").select_related("shelf")
        )
        self.slot_a = self.slots[0]
        self.slot_b = self.slots[1] if len(self.slots) > 1 else None
        if self.slot_b is None:
            self.slot_b = EquipmentSlot.objects.create(
                equipment=self.equipment,
                row_index=0,
                col_index=1,
                width_percent=50,
                slot_label="B",
                shelf=self.shelf,
            )

        self.planogram_a = Planogram.objects.create(
            slot=self.slot_a,
            product=self.product,
            target_quantity=10,
        )
        self.planogram_b = Planogram.objects.create(
            slot=self.slot_b,
            product=self.product,
            target_quantity=10,
        )
        self.batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=100,
            current_quantity=100,
            expiration_date=timezone.localdate() + timedelta(days=365),
            purchase_price="100.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 100})

        self.slot_a.current_qty = 10
        self.slot_a.save(update_fields=["current_qty"])
        self.slot_b.current_qty = 10
        self.slot_b.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(
            planogram__in=(self.planogram_a, self.planogram_b),
            status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        ).delete()

    def test_clearing_one_slot_does_not_zero_sibling(self):
        self.slot_a.current_qty = 10
        self.slot_a.save(update_fields=["current_qty"])
        self.slot_b.current_qty = 10
        self.slot_b.save(update_fields=["current_qty"])

        task = create_shelf_clearing_task(self.admin, self.slot_a.pk)
        accept_shelf_clearing_task(task.pk, self.employee)
        complete_shelf_clearing_task(
            task.pk,
            self.employee,
            raw_code=self.product.sku,
            store_id=self.store.pk,
        )

        self.slot_a.refresh_from_db()
        self.slot_b.refresh_from_db()
        self.assertEqual(self.slot_a.current_qty, 0)
        self.assertEqual(self.slot_b.current_qty, 10)

    def test_placement_complete_does_not_double_qty(self):
        PlacementTask.objects.filter(planogram=self.planogram_a).delete()
        self.slot_a.current_qty = 0
        self.slot_a.save(update_fields=["current_qty"])
        task = PlacementTask.objects.create(
            planogram=self.planogram_a,
            product=self.product,
            equipment=self.equipment,
            quantity=20,
            batch=self.batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        fulfill_placement_scan_requirements(task, self.employee)

        complete_placement_task(task.pk, self.employee, photo_file=None)

        self.slot_a.refresh_from_db()
        self.assertEqual(self.slot_a.current_qty, 20)

    def test_reconcile_merges_duplicate_open_tasks(self):
        PlacementTask.objects.filter(planogram=self.planogram_a).delete()

        keeper = PlacementTask.objects.create(
            planogram=self.planogram_a,
            product=self.product,
            equipment=self.equipment,
            quantity=3,
            batch=self.batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        duplicate = PlacementTask.objects.create(
            planogram=self.planogram_a,
            product=self.product,
            equipment=self.equipment,
            quantity=5,
            batch=self.batch,
            status=PlacementTask.Status.COMPLETED,
            assigned_to=self.employee,
        )
        duplicate_open = PlacementTask(
            pk=duplicate.pk,
            planogram=self.planogram_a,
            product=self.product,
            equipment=self.equipment,
            quantity=5,
            batch=self.batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )

        merged = _merge_open_placement_task_list([keeper, duplicate_open])
        self.assertIsNotNone(merged)
        self.assertEqual(merged.quantity, 8)

        open_tasks = PlacementTask.objects.filter(
            planogram=self.planogram_a,
            status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        )
        self.assertEqual(open_tasks.count(), 1)
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.status, PlacementTask.Status.CANCELLED)

    def test_two_clearing_tasks_different_slots(self):
        self.slot_a.current_qty = 5
        self.slot_a.save(update_fields=["current_qty"])
        self.slot_b.current_qty = 7
        self.slot_b.save(update_fields=["current_qty"])

        task_a = create_shelf_clearing_task(self.admin, self.slot_a.pk)
        task_b = create_shelf_clearing_task(self.admin, self.slot_b.pk)
        accept_shelf_clearing_task(task_a.pk, self.employee)
        complete_shelf_clearing_task(
            task_a.pk,
            self.employee,
            raw_code=self.product.sku,
            store_id=self.store.pk,
        )

        task_b.refresh_from_db()
        self.slot_b.refresh_from_db()
        self.assertEqual(task_b.status, ShelfClearingTask.Status.CREATED)
        self.assertEqual(self.slot_b.current_qty, 7)

    def test_inventory_no_batch_does_not_overwrite_slot_qty(self):
        self.slot_a.current_qty = 3
        self.slot_a.save(update_fields=["current_qty"])
        Inventory.objects.create(
            store=self.store,
            product=self.product,
            shelf=self.shelf,
            status=Inventory.LocationStatus.SHELF,
            quantity=99,
        )
        self.slot_a.refresh_from_db()
        self.assertEqual(self.slot_a.current_qty, 3)

    def test_sync_inventory_from_slot_aggregates_shelf_qty(self):
        self.slot_a.current_qty = 4
        self.slot_a.save(update_fields=["current_qty"])
        self.slot_b.current_qty = 6
        self.slot_b.save(update_fields=["current_qty"])

        sync_inventory_from_slot(self.slot_a, self.product.pk, self.store.pk)

        inv = Inventory.objects.get(
            store=self.store,
            product=self.product,
            batch__isnull=True,
        )
        self.assertEqual(inv.quantity, 10)
