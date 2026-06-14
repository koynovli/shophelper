from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    EquipmentSlot,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    Store,
    Zone,
)
from core.placement_scan_service import (
    record_placement_scan,
    scan_check_for_picking,
)
from core.scan_service import resolve_scan, validate_task_product_scan

User = get_user_model()


class ScanServiceTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Scan Store", address="A")
        self.zone = Zone.objects.create(name="Z", store=self.store, color="#000")
        self.category = Category.objects.create(name="Food")
        self.product = Product.objects.create(
            name="Milk",
            sku="MILK-SCAN",
            gtin="04601234567893",
            category=self.category,
            price="50.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.marked = Product.objects.create(
            name="Marked Juice",
            sku="JUICE-M",
            gtin="04609876543210",
            is_marked=True,
            category=self.category,
            price="80.00",
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.batch = ProductBatch.objects.create(
            product=self.product,
            store=self.store,
            initial_quantity=10,
            current_quantity=10,
            expiration_date=timezone.localdate() + timedelta(days=30),
            purchase_price="40.00",
        )
        self.marked_batch = ProductBatch.objects.create(
            product=self.marked,
            store=self.store,
            initial_quantity=1,
            current_quantity=1,
            serial_number="SN000001",
            expiration_date=timezone.localdate() + timedelta(days=20),
            purchase_price="60.00",
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
        if self.slot is None:
            self.slot = EquipmentSlot.objects.create(
                equipment=self.equipment,
                row_index=0,
                col_index=0,
            )
        self.planogram = Planogram.objects.create(
            slot=self.slot,
            product=self.product,
            target_quantity=5,
        )
        self.placement = PlacementTask.objects.filter(
            planogram=self.planogram,
            status__in=(PlacementTask.Status.CREATED, PlacementTask.Status.PENDING),
        ).first()
        if self.placement is None:
            self.placement = PlacementTask.objects.create(
                planogram=self.planogram,
                product=self.product,
                equipment=self.equipment,
                quantity=2,
                batch=self.batch,
                status=PlacementTask.Status.CREATED,
            )
        else:
            self.placement.batch = self.batch
            self.placement.quantity = 2
            self.placement.save(update_fields=["batch", "quantity"])
        self.employee = User.objects.create_user(
            username="scan_emp",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.client = APIClient()

    def test_resolve_scan_by_sku(self):
        result = resolve_scan("MILK-SCAN", self.store.pk)
        self.assertEqual(result.status, "found")
        self.assertEqual(result.scan_kind, "sku")
        self.assertEqual(result.product.pk, self.product.pk)
        self.assertIsNotNone(result.batch)

    def test_resolve_scan_by_gtin(self):
        result = resolve_scan(self.product.gtin, self.store.pk)
        self.assertEqual(result.status, "found")
        self.assertEqual(result.product.pk, self.product.pk)

    def test_resolve_marked_unit_by_data_matrix(self):
        code = f"01{self.marked.gtin}21SN000001"
        result = resolve_scan(code, self.store.pk)
        self.assertEqual(result.status, "found")
        self.assertEqual(result.scan_kind, "marked_unit")
        self.assertEqual(result.batch.pk, self.marked_batch.pk)

    def test_validate_task_product_scan_rejects_wrong_product(self):
        with self.assertRaises(ValueError):
            validate_task_product_scan(
                task_product_id=self.product.pk,
                raw_code="JUICE-M",
                store_id=self.store.pk,
            )

    def test_scan_resolve_api_requires_auth(self):
        resp = self.client.post(
            "/api/scan/resolve/",
            {"raw_code": "MILK-SCAN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_scan_resolve_api_authenticated(self):
        self.client.force_authenticate(self.employee)
        resp = self.client.post(
            "/api/scan/resolve/",
            {"raw_code": "MILK-SCAN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "found")
        self.assertEqual(resp.data["product"]["sku"], "MILK-SCAN")

    def test_picking_list_groups_by_product(self):
        self.client.force_authenticate(self.employee)
        resp = self.client.get("/api/placement-tasks/picking-list/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["total_qty"], 2)

    def test_scan_check_matches_picking(self):
        check = scan_check_for_picking(
            self.employee,
            raw_code="MILK-SCAN",
            store_id=self.store.pk,
        )
        self.assertTrue(check["matches_picking"])
        self.assertEqual(len(check["suggested_tasks"]), 1)

    def test_scan_check_rejects_unneeded_product(self):
        other = Product.objects.create(
            name="Bread",
            sku="BREAD-1",
            category=self.category,
            price="30.00",
            width=50,
            height=50,
            depth=50,
            weight=300,
        )
        check = scan_check_for_picking(
            self.employee,
            raw_code=other.sku,
            store_id=self.store.pk,
        )
        self.assertFalse(check["matches_picking"])

    def test_record_placement_scan_unmarked(self):
        self.placement.status = PlacementTask.Status.IN_PROGRESS
        self.placement.assigned_to = self.employee
        self.placement.save(update_fields=["status", "assigned_to"])
        task, _ = record_placement_scan(
            self.placement.pk,
            self.employee,
            raw_code="MILK-SCAN",
            store_id=self.store.pk,
        )
        self.assertEqual(task.scans.count(), 1)

    def test_placement_complete_requires_product_scans(self):
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/placement-tasks/{self.placement.pk}/accept/")
        done = self.client.post(f"/api/placement-tasks/{self.placement.pk}/complete/")
        self.assertEqual(done.status_code, 400)

        self.client.post(
            f"/api/placement-tasks/{self.placement.pk}/scan-unit/",
            {"raw_code": "MILK-SCAN"},
            format="json",
        )
        self.client.post(
            f"/api/placement-tasks/{self.placement.pk}/scan-unit/",
            {"raw_code": "MILK-SCAN"},
            format="json",
        )
        done = self.client.post(f"/api/placement-tasks/{self.placement.pk}/complete/")
        self.assertEqual(done.status_code, 200)
