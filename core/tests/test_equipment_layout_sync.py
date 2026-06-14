from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.equipment_layout_sync import LAYOUT_CHANGE_BLOCKED_MSG
from core.models import (
    Category,
    Equipment,
    EquipmentSlot,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    ShelfClearingTask,
    StockItem,
    Store,
    Zone,
)

User = get_user_model()


class EquipmentLayoutSyncTests(TestCase):
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
        self.client.force_authenticate(self.admin)

    def _create_shelf(self, rows_count: int = 4) -> Equipment:
        return Equipment.objects.create(
            name="Rack",
            zone=self.zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=rows_count,
        )

    def _product(self) -> Product:
        return Product.objects.create(
            name="Milk",
            sku="MILK-L",
            category=self.category,
            price="50.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )

    def test_resync_rows_count_reduces_grid_slots(self):
        equipment = self._create_shelf(rows_count=4)
        self.assertEqual(EquipmentSlot.objects.filter(equipment=equipment).count(), 16)

        equipment.rows_count = 2
        equipment.save(update_fields=["rows_count"])
        from core.equipment_layout_sync import resync_equipment_layout

        resync_equipment_layout(equipment)

        self.assertEqual(EquipmentSlot.objects.filter(equipment=equipment).count(), 8)

    def test_resync_shelf_to_hanger(self):
        equipment = self._create_shelf(rows_count=4)
        equipment.type = Equipment.EquipmentType.HANGER
        equipment.rows_count = 2
        equipment.save(update_fields=["type", "rows_count"])
        from core.equipment_layout_sync import resync_equipment_layout

        resync_equipment_layout(equipment)

        slots = list(EquipmentSlot.objects.filter(equipment=equipment).order_by("row_index"))
        self.assertEqual(len(slots), 2)
        for slot in slots:
            self.assertEqual(slot.col_index, 0)
            self.assertEqual(slot.width_percent, 100.0)

    def test_resync_shelf_to_mannequin_removes_shelves(self):
        equipment = self._create_shelf(rows_count=2)
        self.assertTrue(equipment.shelves.exists())

        equipment.type = Equipment.EquipmentType.MANNEQUIN
        equipment.rows_count = 3
        equipment.save(update_fields=["type", "rows_count"])
        from core.equipment_layout_sync import resync_equipment_layout

        resync_equipment_layout(equipment)

        self.assertEqual(EquipmentSlot.objects.filter(equipment=equipment).count(), 3)
        self.assertFalse(equipment.shelves.exists())

    def test_patch_resync_via_api(self):
        equipment = self._create_shelf(rows_count=4)
        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {"rows_count": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["slots"]), 8)

    def test_patch_blocked_when_slot_has_stock(self):
        equipment = self._create_shelf(rows_count=4)
        slot = equipment.slots.first()
        slot.current_qty = 3
        slot.save(update_fields=["current_qty"])

        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {"rows_count": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("товар", str(resp.data).lower())

    def test_patch_blocked_when_placement_task_created(self):
        equipment = self._create_shelf(rows_count=4)
        slot = equipment.slots.first()
        product = self._product()
        planogram = Planogram.objects.create(
            slot=slot,
            product=product,
            target_quantity=5,
        )
        PlacementTask.objects.create(
            planogram=planogram,
            product=product,
            equipment=equipment,
            quantity=2,
            status=PlacementTask.Status.CREATED,
        )

        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {"type": Equipment.EquipmentType.HANGER},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(LAYOUT_CHANGE_BLOCKED_MSG.split(".")[0], str(resp.data))

    def test_patch_blocked_when_placement_task_in_progress(self):
        equipment = self._create_shelf(rows_count=4)
        slot = equipment.slots.first()
        product = self._product()
        planogram = Planogram.objects.create(
            slot=slot,
            product=product,
            target_quantity=5,
        )
        PlacementTask.objects.create(
            planogram=planogram,
            product=product,
            equipment=equipment,
            quantity=2,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )

        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {"rows_count": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_modification_info_lists_blockers_and_occupied_slots(self):
        equipment = self._create_shelf(rows_count=4)
        slot = equipment.slots.first()
        product = self._product()
        Planogram.objects.create(slot=slot, product=product, target_quantity=5)
        slot.current_qty = 4
        slot.save(update_fields=["current_qty"])

        resp = self.client.get(f"/api/floor-equipment/{equipment.pk}/modification-info/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["can_modify_layout"])
        self.assertFalse(resp.data["can_delete"])
        self.assertTrue(len(resp.data["blockers"]) >= 1)
        self.assertEqual(len(resp.data["occupied_slots"]), 1)
        self.assertEqual(resp.data["occupied_slots"][0]["current_qty"], 4)

    def test_delete_equipment_blocked_with_stock(self):
        equipment = self._create_shelf(rows_count=4)
        slot = equipment.slots.first()
        slot.current_qty = 2
        slot.save(update_fields=["current_qty"])

        resp = self.client.delete(f"/api/floor-equipment/{equipment.pk}/")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Equipment.objects.filter(pk=equipment.pk).exists())
