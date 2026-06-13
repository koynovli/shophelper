from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Category,
    Company,
    Inventory,
    Product,
    ProductBatch,
    Store,
    Supplier,
    SupplyOrder,
    SupplyOrderItem,
)

User = get_user_model()


class SupplyOrderApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Тест ООО")
        self.store = Store.objects.create(name="Магазин 1", address="ул. Тест, 1")
        self.category = Category.objects.create(name="Бакалея")
        self.product = Product.objects.create(
            name="Рис",
            sku="RICE-001",
            category=self.category,
            price=Decimal("120.00"),
            width=100,
            height=200,
            depth=50,
            weight=1000,
        )
        self.admin = User.objects.create_user(
            username="admin_so",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.employee = User.objects.create_user(
            username="emp_so",
            password="pass",
            role=User.Role.EMPLOYEE,
        )
        self.client = APIClient()
        self.order_payload = {
            "status": "ordered",
            "items": [
                {
                    "product": self.product.pk,
                    "quantity": 10,
                    "purchase_price": "72.50",
                }
            ],
        }

    def test_admin_create_order_no_batches(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        assert resp.status_code == 201
        order = SupplyOrder.objects.get(pk=resp.data["id"])
        assert order.status == SupplyOrder.Status.ORDERED
        assert order.total_amount == Decimal("725.00")
        assert order.items.count() == 1
        item = order.items.first()
        assert item.quantity == 10
        assert item.purchase_price == Decimal("72.50")
        assert not ProductBatch.objects.filter(supply_item=item).exists()

    def test_employee_cannot_create_order(self):
        self.client.force_authenticate(self.employee)
        resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        assert resp.status_code == 403

    def test_receive_via_receiving_task(self):
        from core.models import SupplyReceivingTask

        self.client.force_authenticate(self.admin)
        create_resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        order_id = create_resp.data["id"]
        item_id = create_resp.data["items"][0]["id"]
        task = SupplyReceivingTask.objects.get(supply_order_id=order_id)
        exp = (timezone.now().date() + timedelta(days=30)).isoformat()

        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task.pk}/accept/")
        recv_resp = self.client.post(
            f"/api/receiving-tasks/{task.pk}/complete/",
            {
                "lines": [
                    {
                        "item_id": item_id,
                        "expiration_date": exp,
                        "actual_quantity": 10,
                    }
                ]
            },
            format="json",
        )
        assert recv_resp.status_code == 200
        order = SupplyOrder.objects.get(pk=order_id)
        assert order.status == SupplyOrder.Status.RECEIVED
        assert order.total_cost == Decimal("725.00")
        batch = ProductBatch.objects.get(supply_item_id=item_id)
        assert batch.current_quantity == 10
        assert Inventory.objects.filter(batch=batch, quantity=10).exists()

    def test_receive_twice_rejected(self):
        from core.models import SupplyReceivingTask

        self.client.force_authenticate(self.admin)
        create_resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        order_id = create_resp.data["id"]
        item_id = create_resp.data["items"][0]["id"]
        task = SupplyReceivingTask.objects.get(supply_order_id=order_id)
        exp = (timezone.now().date() + timedelta(days=30)).isoformat()
        payload = {
            "lines": [{"item_id": item_id, "expiration_date": exp, "actual_quantity": 10}],
        }
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task.pk}/accept/")
        self.client.post(
            f"/api/receiving-tasks/{task.pk}/complete/", payload, format="json"
        )
        again = self.client.post(
            f"/api/receiving-tasks/{task.pk}/complete/", payload, format="json"
        )
        assert again.status_code == 400

    def test_create_supplier_and_order(self):
        self.client.force_authenticate(self.admin)
        sup_resp = self.client.post(
            "/api/suppliers/",
            {"name": "Оптовик", "inn": "7701234567", "contact_info": "test@mail.ru"},
            format="json",
        )
        assert sup_resp.status_code == 201
        payload = {
            **self.order_payload,
            "supplier": sup_resp.data["id"],
        }
        order_resp = self.client.post("/api/supply-orders/", payload, format="json")
        assert order_resp.status_code == 201
        order = SupplyOrder.objects.get(pk=order_resp.data["id"])
        assert order.supplier_id == sup_resp.data["id"]

    def _create_draft(self):
        self.client.force_authenticate(self.admin)
        payload = {**self.order_payload, "status": "draft"}
        return self.client.post("/api/supply-orders/", payload, format="json")

    def test_patch_draft_updates_items_and_total(self):
        create_resp = self._create_draft()
        order_id = create_resp.data["id"]
        patch_resp = self.client.patch(
            f"/api/supply-orders/{order_id}/",
            {
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": 5,
                        "purchase_price": "80.00",
                    }
                ]
            },
            format="json",
        )
        assert patch_resp.status_code == 200
        order = SupplyOrder.objects.get(pk=order_id)
        assert order.total_amount == Decimal("400.00")
        assert order.items.count() == 1
        assert order.items.first().quantity == 5

    def test_patch_ordered_rejected(self):
        self.client.force_authenticate(self.admin)
        create_resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        order_id = create_resp.data["id"]
        patch_resp = self.client.patch(
            f"/api/supply-orders/{order_id}/",
            {"items": self.order_payload["items"]},
            format="json",
        )
        assert patch_resp.status_code == 400

    def test_submit_draft_to_ordered(self):
        create_resp = self._create_draft()
        order_id = create_resp.data["id"]
        submit_resp = self.client.post(
            f"/api/supply-orders/{order_id}/submit/", format="json"
        )
        assert submit_resp.status_code == 200
        assert submit_resp.data["status"] == "ordered"
        again = self.client.post(
            f"/api/supply-orders/{order_id}/submit/", format="json"
        )
        assert again.status_code == 400

    def test_receive_draft_forbidden(self):
        create_resp = self._create_draft()
        order_id = create_resp.data["id"]
        recv = self.client.post(f"/api/supply-orders/{order_id}/receive/")
        assert recv.status_code == 403

    def test_delete_draft_ok_ordered_rejected(self):
        draft_resp = self._create_draft()
        draft_id = draft_resp.data["id"]
        del_draft = self.client.delete(f"/api/supply-orders/{draft_id}/")
        assert del_draft.status_code == 204
        assert not SupplyOrder.objects.filter(pk=draft_id).exists()

        ordered_resp = self.client.post(
            "/api/supply-orders/", self.order_payload, format="json"
        )
        ordered_id = ordered_resp.data["id"]
        del_ordered = self.client.delete(f"/api/supply-orders/{ordered_id}/")
        assert del_ordered.status_code == 400

    def test_supplier_invalid_inn(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/suppliers/",
            {"name": "Bad", "inn": "123"},
            format="json",
        )
        assert resp.status_code == 400

    def test_supplier_duplicate_inn(self):
        self.client.force_authenticate(self.admin)
        Supplier.objects.create(name="First", inn="7701234567")
        resp = self.client.post(
            "/api/suppliers/",
            {"name": "Second", "inn": "7701234567"},
            format="json",
        )
        assert resp.status_code == 400
