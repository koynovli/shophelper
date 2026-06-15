from __future__ import annotations

from decimal import Decimal

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

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
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
    SupplyReceivingTask,
    Zone,
)
from core.placement_execution import PlacementExecutionError, complete_placement_task
from core.placement_scan_service import record_placement_scan
from core.product_units import (
    compute_bulk_density_kg_m3,
    format_quantity,
    grams_to_kg,
    kg_to_grams,
    weight_sufficient_threshold_grams,
    weight_task_scans_sufficient,
)
from core.spatial_engine import (
    calculate_slot_max_capacity,
    refresh_slot_max_capacity,
    slot_volume_m3,
)
from core.supply_receiving_service import complete_receiving_task, create_receiving_task
from shophelper.utils import parse_variable_weight_ean13

User = get_user_model()


class WeighedProductTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Co")
        self.store = Store.objects.create(name="Store", address="Addr")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Produce")
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
            name="Apples",
            sku="12345",
            category=self.category,
            price="120.00",
            width=50,
            height=50,
            depth=50,
            weight=150,
            sale_unit=Product.SaleUnit.WEIGHT,
            allowed_equipment_types=["box"],
            bulk_density=compute_bulk_density_kg_m3(50, 50, 50, 150),
        )
        self.equipment = Equipment.objects.create(
            name="Basket",
            zone=self.zone,
            type=Equipment.EquipmentType.BOX,
            pos_x=0,
            pos_y=0,
            width=80,
            height=40,
            rows_count=1,
        )
        self.slot = self.equipment.slots.first()
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=kg_to_grams("5"),
        )
        self.slot.refresh_from_db()

    def test_product_weight_unit_validation(self):
        self.client.force_authenticate(self.admin)
        bad = self.client.post(
            "/api/products/",
            {
                "name": "Bad",
                "sku": "BAD-W",
                "category": self.category.pk,
                "price": "10.00",
                "width": 1,
                "height": 1,
                "depth": 1,
                "weight": 100,
                "sale_unit": "weight",
                "is_marked": True,
                "allowed_equipment_types": ["box"],
            },
            format="json",
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            "/api/products/",
            {
                "name": "Pears",
                "sku": "54321",
                "category": self.category.pk,
                "price": "90.00",
                "width": 50,
                "height": 50,
                "depth": 50,
                "weight": 150,
                "sale_unit": "weight",
                "allowed_equipment_types": ["box"],
            },
            format="json",
        )
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(float(ok.data["bulk_density"]), 660.0)

    def test_compute_bulk_density_from_dimensions(self):
        self.assertEqual(compute_bulk_density_kg_m3(50, 50, 50, 150), 660.0)
        self.assertIsNone(compute_bulk_density_kg_m3(0, 50, 50, 150))

    def test_kg_to_grams_conversion(self):
        self.assertEqual(kg_to_grams("1.250"), 1250)
        self.assertEqual(str(grams_to_kg(1250)), "1.250")

    def test_parse_variable_weight_ean13(self):
        parsed = parse_variable_weight_ean13("2312345012507")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["plu"], "12345")
        self.assertEqual(parsed["weight_grams"], 1250)

    def test_box_planogram_target_weight_capacity(self):
        phys = calculate_slot_max_capacity(self.slot, self.product)
        cap = refresh_slot_max_capacity(self.slot, self.product)
        self.assertEqual(cap, phys)
        self.assertGreater(cap, kg_to_grams("5"))
        self.assertEqual(self.planogram.target_quantity, kg_to_grams("5"))

    def test_weight_box_physics_capacity(self):
        volume = slot_volume_m3(self.slot)
        self.assertGreater(volume, 0)
        density = compute_bulk_density_kg_m3(50, 50, 50, 150)
        expected = int(volume * density * 1000.0)
        cap = calculate_slot_max_capacity(self.slot, self.product)
        self.assertEqual(cap, expected)
        self.assertLess(cap, kg_to_grams("100"))

    def test_box_120x60_realistic_weight_capacity(self):
        equipment = Equipment.objects.create(
            name="Large basket",
            zone=self.zone,
            type=Equipment.EquipmentType.BOX,
            pos_x=10,
            pos_y=10,
            width=120,
            height=60,
            rows_count=1,
        )
        slot = equipment.slots.first()
        product = Product.objects.create(
            name="Apples large",
            sku="APL-120",
            category=self.category,
            price="100.00",
            width=50,
            height=50,
            depth=50,
            weight=150,
            sale_unit=Product.SaleUnit.WEIGHT,
            allowed_equipment_types=["box"],
            bulk_density=compute_bulk_density_kg_m3(50, 50, 50, 150),
        )
        cap = calculate_slot_max_capacity(slot, product)
        self.assertGreater(cap, kg_to_grams("20"))
        self.assertLess(cap, kg_to_grams("150"))

    def test_create_weight_planogram_via_target_quantity_kg(self):
        self.planogram.delete()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity_kg": "5",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        planogram = Planogram.objects.get(slot=self.slot, product=self.product)
        self.assertEqual(planogram.target_quantity, kg_to_grams("5"))

    def test_weight_planogram_rejects_target_quantity_field(self):
        self.planogram.delete()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity": 2_700_000,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("target_quantity_kg", str(resp.data).lower())

    def test_weight_planogram_rejects_excessive_target_kg(self):
        self.planogram.delete()
        phys_kg = float(grams_to_kg(calculate_slot_max_capacity(self.slot, self.product)))
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/planograms/",
            {
                "slot": self.slot.pk,
                "product": self.product.pk,
                "target_quantity_kg": str(phys_kg + 1000),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("target_quantity_kg", resp.data)

    def test_receiving_weight_product_creates_batch_in_grams(self):
        company = Company.objects.create(name="Co")
        supplier = Supplier.objects.create(name="Sup", inn="1234567890")
        order = SupplyOrder.objects.create(
            company=company,
            store=self.store,
            supplier=supplier,
            status=SupplyOrder.Status.ORDERED,
            created_by=self.admin,
        )
        item = SupplyOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=kg_to_grams("3.5"),
            purchase_price=Decimal("80.00"),
        )
        task = create_receiving_task(order, self.admin)
        from core.supply_receiving_service import accept_receiving_task

        accept_receiving_task(task.pk, self.employee)
        complete_receiving_task(
            task.pk,
            self.employee,
            lines=[
                {
                    "item_id": item.pk,
                    "actual_quantity_kg": "3.5",
                }
            ],
        )
        batch = ProductBatch.objects.get(product=self.product, store=self.store)
        self.assertEqual(batch.current_quantity, 3500)
        item.refresh_from_db()
        self.assertEqual(item.actual_quantity, 3500)

    def test_weight_task_threshold_helpers(self):
        task_qty = kg_to_grams("2.5")
        self.assertEqual(weight_sufficient_threshold_grams(task_qty), kg_to_grams("2"))
        self.assertTrue(weight_task_scans_sufficient(kg_to_grams("2"), task_qty))
        self.assertFalse(weight_task_scans_sufficient(kg_to_grams("1.9"), task_qty))

    def test_placement_weight_scans_sum_to_complete(self):
        batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10000,
            current_quantity=10000,
            expiration_date=date(2099, 12, 31),
            purchase_price="80.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 10000})
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])

        PlacementTask.objects.filter(planogram=self.planogram).delete()
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=kg_to_grams("2.5"),
            batch=batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )

        record_placement_scan(
            task.pk,
            self.employee,
            raw_code="",
            store_id=self.store.pk,
            weight_kg="1.0",
        )
        record_placement_scan(
            task.pk,
            self.employee,
            raw_code="",
            store_id=self.store.pk,
            weight_kg="1.0",
        )

        complete_placement_task(task.pk, self.employee, photo_file=None)

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.current_qty, 2000)
        self.assertEqual(format_quantity(self.product, self.slot.current_qty), "2.000 кг")

    def test_placement_no_double_grams(self):
        batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=5000,
            current_quantity=5000,
            expiration_date=date(2099, 12, 31),
            purchase_price="80.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 5000})
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])

        PlacementTask.objects.filter(planogram=self.planogram).delete()
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=kg_to_grams("2.5"),
            batch=batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        record_placement_scan(
            task.pk,
            self.employee,
            raw_code="",
            store_id=self.store.pk,
            weight_kg="2.0",
        )
        complete_placement_task(task.pk, self.employee, photo_file=None)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.current_qty, 2000)

    def test_create_weight_supply_order_with_quantity_kg(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/supply-orders/",
            {
                "status": "draft",
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity_kg": "3.5",
                        "purchase_price": "80.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        order = SupplyOrder.objects.get(pk=resp.data["id"])
        self.assertEqual(order.total_amount, Decimal("280.00"))
        item = order.items.first()
        self.assertEqual(item.quantity, 3500)
        self.assertEqual(resp.data["items"][0]["quantity_kg"], "3.500")

    def test_update_draft_weight_order_recalculates_total(self):
        supplier = Supplier.objects.create(name="Sup", inn="1234567890")
        order = SupplyOrder.objects.create(
            company=self.company,
            store=self.store,
            supplier=supplier,
            status=SupplyOrder.Status.DRAFT,
            created_by=self.admin,
        )
        SupplyOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=kg_to_grams("2"),
            purchase_price=Decimal("100.00"),
        )
        order.total_amount = Decimal("200.00")
        order.save(update_fields=["total_amount"])

        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/supply-orders/{order.pk}/",
            {
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity_kg": "2.5",
                        "purchase_price": "100.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("250.00"))
        item = order.items.first()
        self.assertEqual(item.quantity, 2500)

    def test_capacity_preview_weight_box(self):
        self.client.force_authenticate(self.admin)
        expected = calculate_slot_max_capacity(self.slot, self.product)
        resp = self.client.get(
            f"/api/slots/{self.slot.pk}/capacity-preview/",
            {"product": self.product.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["quantity_unit"], "kg")
        self.assertEqual(resp.data["max_capacity"], expected)
        self.assertEqual(resp.data["max_capacity_kg"], str(grams_to_kg(expected)))

    def test_capacity_preview_piece_box(self):
        piece = Product.objects.create(
            name="Rice bag",
            sku="RICE-BAG",
            category=self.category,
            price="90.00",
            width=100,
            height=100,
            depth=100,
            weight=500,
            sale_unit=Product.SaleUnit.PIECE,
            allowed_equipment_types=["box"],
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.get(
            f"/api/slots/{self.slot.pk}/capacity-preview/",
            {"product": piece.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["quantity_unit"], "piece")
        self.assertIsNone(resp.data["max_capacity_kg"])
        self.assertGreater(resp.data["max_capacity"], 0)

    def test_adjust_qty_kg_triggers_reconcile(self):
        ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10000,
            current_quantity=10000,
            expiration_date=date(2099, 12, 31),
            purchase_price="80.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(
            product=self.product, defaults={"quantity": 10000}
        )
        self.slot.current_qty = kg_to_grams("5")
        self.slot.max_capacity = kg_to_grams("5")
        self.slot.save(update_fields=["current_qty", "max_capacity"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()

        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/slots/{self.slot.pk}/adjust-qty/",
            {"delta_kg": "-3.6"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.current_qty, 1400)
        self.assertTrue(
            PlacementTask.objects.filter(
                planogram=self.planogram,
                status=PlacementTask.Status.CREATED,
            ).exists()
        )

    def test_weight_complete_at_80_percent_of_task(self):
        batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10000,
            current_quantity=10000,
            expiration_date=date(2099, 12, 31),
            purchase_price="80.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 10000})
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=kg_to_grams("2.5"),
            batch=batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        record_placement_scan(
            task.pk,
            self.employee,
            raw_code="",
            store_id=self.store.pk,
            weight_kg="2.0",
        )
        complete_placement_task(task.pk, self.employee, photo_file=None)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.current_qty, 2000)

    def test_weight_complete_rejects_below_80_percent_of_task(self):
        batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10000,
            current_quantity=10000,
            expiration_date=date(2099, 12, 31),
            purchase_price="80.00",
            is_active=True,
        )
        StockItem.objects.update_or_create(product=self.product, defaults={"quantity": 10000})
        self.slot.current_qty = 0
        self.slot.save(update_fields=["current_qty"])
        PlacementTask.objects.filter(planogram=self.planogram).delete()
        task = PlacementTask.objects.create(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=kg_to_grams("2.5"),
            batch=batch,
            status=PlacementTask.Status.IN_PROGRESS,
            assigned_to=self.employee,
        )
        record_placement_scan(
            task.pk,
            self.employee,
            raw_code="",
            store_id=self.store.pk,
            weight_kg="1.9",
        )
        with self.assertRaises(PlacementExecutionError):
            complete_placement_task(task.pk, self.employee, photo_file=None)

    def test_task_destination_for_box(self):
        from core.placement_scan_service import format_task_destination

        task = PlacementTask(
            planogram=self.planogram,
            product=self.product,
            equipment=self.equipment,
            quantity=1000,
            status=PlacementTask.Status.CREATED,
        )
        dest = format_task_destination(task)
        self.assertIn("Бокс / корзина", dest)
