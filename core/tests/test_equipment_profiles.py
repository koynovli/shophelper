from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.equipment_profiles import (
    MANNEQUIN_ZONE_LABELS,
    box_naval_fill_height_cm,
    default_rows_count,
    default_slots_spec,
    layout_mode,
    needs_shelves,
    shelf_dimensions_for_equipment,
)
from core.models import Category, Equipment, EquipmentSlot, Planogram, Product, Shelf, Store, Zone
from core.spatial_engine import calculate_slot_max_capacity

User = get_user_model()


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

    def test_box_shelf_dimensions_use_footprint_not_width_as_height(self):
        equipment = self._create_equipment(Equipment.EquipmentType.BOX, rows_count=1)
        equipment.width = 120
        equipment.height = 60
        equipment.save(update_fields=["width", "height"])
        dims = shelf_dimensions_for_equipment(equipment, 1)
        self.assertEqual(dims["width"], 120.0)
        self.assertEqual(dims["depth"], 60.0)
        self.assertEqual(dims["height"], box_naval_fill_height_cm(equipment))
        self.assertLess(dims["height"], 60.0)

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


class SlotCapacityTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Cat")
        self.admin = User.objects.create_user(
            username="admin_cap",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.client = APIClient()
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
        self.slot = (
            EquipmentSlot.objects.filter(equipment=self.equipment)
            .order_by("row_index", "col_index")
            .first()
        )
        self.product = Product.objects.create(
            name="Water",
            sku="W-CAP-1",
            category=self.category,
            price="30.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
            is_stackable=True,
        )
        Shelf.objects.filter(equipment=self.equipment).delete()
        EquipmentSlot.objects.filter(pk=self.slot.pk).update(shelf_id=None, max_capacity=0)
        self.slot.refresh_from_db()

    def test_capacity_without_shelf_row(self):
        cap = calculate_slot_max_capacity(self.slot, self.product)
        self.assertGreater(cap, 0)

    def test_capacity_tall_product_single_facing_layer(self):
        tall = Product.objects.create(
            name="Tall bottle",
            sku="TALL-1",
            category=self.category,
            price="50.00",
            width=70,
            height=200,
            depth=70,
            weight=500,
            is_stackable=True,
        )
        cap = calculate_slot_max_capacity(self.slot, tall)
        self.assertGreater(cap, 1)

    def test_legacy_shelving_type_capacity(self):
        equipment = Equipment.objects.create(
            name="Legacy rack",
            zone=self.zone,
            type="shelving",
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=2,
        )
        slot = EquipmentSlot.objects.filter(equipment=equipment).order_by("row_index", "col_index").first()
        Shelf.objects.filter(equipment=equipment).delete()
        EquipmentSlot.objects.filter(pk=slot.pk).update(shelf_id=None)
        cap = calculate_slot_max_capacity(slot, self.product)
        self.assertGreater(cap, 0)

    def test_capacity_preview_api(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.slot.max_capacity, 0)
        resp = self.client.get(
            f"/api/slots/{self.slot.pk}/capacity-preview/",
            {"product": self.product.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(int(resp.data["max_capacity"]), 0)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.max_capacity, 0)

    def test_planogram_save_refreshes_slot_max_capacity(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity": 5,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.slot.refresh_from_db()
        self.assertGreater(self.slot.max_capacity, 0)
        self.assertTrue(Planogram.objects.filter(slot=self.slot, product=self.product).exists())

    def test_planogram_delete_resets_slot_capacity(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity": 5,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        planogram = Planogram.objects.get(slot=self.slot, product=self.product)
        self.slot.refresh_from_db()
        self.assertGreater(self.slot.max_capacity, 0)

        del_resp = self.client.delete(f"/api/planograms/{planogram.pk}/")
        self.assertEqual(del_resp.status_code, 204)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.max_capacity, 0)
        self.assertEqual(self.slot.current_qty, 0)

    def test_folded_apparel_fits_shelf_slot(self):
        tshirt = Product.objects.create(
            name="T-shirt",
            sku="TS-1",
            category=self.category,
            price="20.00",
            width=300,
            height=50,
            depth=250,
            weight=200,
            is_stackable=False,
            allowed_equipment_types=["shelf"],
        )
        EquipmentSlot.objects.filter(pk=self.slot.pk).update(width_percent=100)
        self.slot.refresh_from_db()
        cap = calculate_slot_max_capacity(self.slot, tshirt)
        self.assertGreater(cap, 1)

    def test_apparel_planogram_on_shelf_allowed(self):
        tshirt = Product.objects.create(
            name="T-shirt 2",
            sku="TS-2",
            category=self.category,
            price="20.00",
            width=300,
            height=50,
            depth=250,
            weight=200,
            is_stackable=False,
            allowed_equipment_types=["shelf"],
        )
        EquipmentSlot.objects.filter(pk=self.slot.pk).update(width_percent=100)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {"slot": self.slot.pk, "product": tshirt.pk, "target_quantity": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)


class RowSlotLayoutTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.admin = User.objects.create_user(
            username="admin_rows",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.client = APIClient()

    def _create_shelf(self, rows_count: int = 2) -> Equipment:
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

    def test_custom_layout_builds_variable_slots(self):
        equipment = self._create_shelf(rows_count=2)
        equipment.row_slot_layouts = [
            {"slot_count": 4, "widths": [25, 25, 25, 25]},
            {"slot_count": 2, "widths": [60, 40]},
        ]
        specs = default_slots_spec(equipment)
        row0 = [s for s in specs if s.row_index == 0]
        row1 = [s for s in specs if s.row_index == 1]
        self.assertEqual(len(row0), 4)
        self.assertEqual(len(row1), 2)
        self.assertEqual([round(s.width_percent) for s in row1], [60, 40])

    def test_patch_layout_resyncs_slots(self):
        equipment = self._create_shelf(rows_count=2)
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {
                "row_slot_layouts": [
                    {"slot_count": 1, "widths": [100]},
                    {"slot_count": 3, "widths": [40, 30, 30]},
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        row0 = EquipmentSlot.objects.filter(equipment=equipment, row_index=0).count()
        row1 = EquipmentSlot.objects.filter(equipment=equipment, row_index=1).count()
        self.assertEqual(row0, 1)
        self.assertEqual(row1, 3)

    def test_invalid_layout_rejected(self):
        equipment = self._create_shelf(rows_count=2)
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/floor-equipment/{equipment.pk}/",
            {
                "row_slot_layouts": [
                    {"slot_count": 2, "widths": [50, 30]},
                    {"slot_count": 2, "widths": [50, 50]},
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
