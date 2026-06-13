from __future__ import annotations

from django.test import TestCase

from core.equipment_profiles import (
    MANNEQUIN_ZONE_LABELS,
    default_rows_count,
    default_slots_spec,
    layout_mode,
    needs_shelves,
)
from core.models import Category, Equipment, EquipmentSlot, Planogram, Product, Store, Zone


class EquipmentProfileTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Cat")

    def _create_equipment(self, eq_type: str, rows_count: int = 4) -> Equipment:
        return Equipment.objects.create(
            name=f"{eq_type}-1",
            zone=self.zone,
            type=eq_type,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=rows_count,
        )

    def test_shelf_generates_grid_slots(self):
        equipment = self._create_equipment(Equipment.EquipmentType.SHELF, rows_count=2)
        slots = list(EquipmentSlot.objects.filter(equipment=equipment).order_by("row_index", "col_index"))
        self.assertEqual(len(slots), 8)
        self.assertEqual(layout_mode(equipment.type), "grid")
        self.assertTrue(needs_shelves(equipment.type))

    def test_hanger_generates_one_slot_per_row(self):
        equipment = self._create_equipment(Equipment.EquipmentType.HANGER, rows_count=2)
        slots = list(EquipmentSlot.objects.filter(equipment=equipment).order_by("row_index"))
        self.assertEqual(len(slots), 2)
        for slot in slots:
            self.assertEqual(slot.col_index, 0)
            self.assertEqual(slot.width_percent, 100.0)
        self.assertEqual(layout_mode(equipment.type), "linear")

    def test_box_generates_single_slot(self):
        equipment = self._create_equipment(Equipment.EquipmentType.BOX, rows_count=1)
        slots = list(EquipmentSlot.objects.filter(equipment=equipment))
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].width_percent, 100.0)
        self.assertEqual(layout_mode(equipment.type), "single")

    def test_mannequin_generates_three_zones_without_shelves(self):
        equipment = self._create_equipment(Equipment.EquipmentType.MANNEQUIN, rows_count=3)
        slots = list(EquipmentSlot.objects.filter(equipment=equipment).order_by("row_index"))
        self.assertEqual(len(slots), 3)
        self.assertFalse(needs_shelves(equipment.type))
        self.assertFalse(equipment.shelves.exists())
        labels = [s.slot_label for s in slots]
        self.assertEqual(labels, list(MANNEQUIN_ZONE_LABELS))

    def test_default_slots_spec_respects_rows_for_hanger_cap(self):
        equipment = self._create_equipment(Equipment.EquipmentType.HANGER, rows_count=5)
        specs = default_slots_spec(equipment)
        self.assertEqual(len(specs), 2)

    def test_default_rows_count_by_type(self):
        self.assertEqual(default_rows_count(Equipment.EquipmentType.MANNEQUIN), 3)
        self.assertEqual(default_rows_count(Equipment.EquipmentType.HANGER), 2)


class PlanogramEquipmentCompatibilityTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Cat")
        self.equipment = Equipment.objects.create(
            name="Mannequin",
            zone=self.zone,
            type=Equipment.EquipmentType.MANNEQUIN,
            pos_x=0,
            pos_y=0,
            width=80,
            height=180,
            rows_count=3,
        )
        self.slot = EquipmentSlot.objects.filter(equipment=self.equipment).order_by("row_index").first()
        self.product = Product.objects.create(
            name="Shirt",
            sku="SHIRT-1",
            category=self.category,
            price="100.00",
            width=300,
            height=20,
            depth=200,
            weight=200,
            allowed_equipment_types=[Equipment.EquipmentType.SHELF],
        )

    def test_planogram_rejects_incompatible_product_on_mannequin(self):
        from rest_framework import serializers

        from core.serializers import PlanogramWriteSerializer

        ser = PlanogramWriteSerializer(
            data={
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity": 1,
            }
        )
        with self.assertRaises(serializers.ValidationError) as ctx:
            ser.is_valid(raise_exception=True)
        self.assertIn("типа оборудования", str(ctx.exception))

    def test_planogram_allows_compatible_product(self):
        self.product.allowed_equipment_types = [Equipment.EquipmentType.MANNEQUIN]
        self.product.save(update_fields=["allowed_equipment_types"])

        planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=1,
        )
        self.assertEqual(planogram.target_quantity, 1)
