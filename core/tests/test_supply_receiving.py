from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.batch_expiry import FAR_FUTURE_EXPIRY
from core.models import (
    Category,
    Company,
    Inventory,
    Product,
    ProductBatch,
    Store,
    SupplyOrder,
    SupplyReceivingTask,
)

User = get_user_model()


class SupplyReceivingTaskTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Тест ООО")
        self.store = Store.objects.create(name="Магазин 1", address="ул. Тест, 1")
        self.category = Category.objects.create(name="Бакалея")
        self.product = Product.objects.create(
            name="Рис",
            sku="RICE-REC",
            category=self.category,
            price=Decimal("120.00"),
            width=100,
            height=200,
            depth=50,
            weight=1000,
            shelf_life_days=30,
        )
        self.admin = User.objects.create_user(
            username="admin_rec",
            password="pass",
            role=User.Role.ADMIN,
            store=self.store,
        )
        self.employee = User.objects.create_user(
            username="emp_rec",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.other = User.objects.create_user(
            username="emp_other",
            password="pass",
            role=User.Role.EMPLOYEE,
            store=self.store,
        )
        self.client = APIClient()

    def _create_ordered_with_task(self, assigned_to=None):
        self.client.force_authenticate(self.admin)
        body = {
            "status": "ordered",
            "items": [
                {
                    "product": self.product.pk,
                    "quantity": 10,
                    "purchase_price": "50.00",
                }
            ],
        }
        if assigned_to is not None:
            body["assigned_to"] = assigned_to.pk
        resp = self.client.post("/api/supply-orders/", body, format="json")
        assert resp.status_code == 201
        order_id = resp.data["id"]
        task = SupplyReceivingTask.objects.get(supply_order_id=order_id)
        return order_id, task.pk, resp.data["items"][0]["id"]

    def _manufacture_date(self, days_ago: int = 2) -> str:
        return (timezone.now().date() - timedelta(days=days_ago)).isoformat()

    def test_submit_creates_receiving_task(self):
        order_id, task_id, _ = self._create_ordered_with_task()
        order = SupplyOrder.objects.get(pk=order_id)
        assert order.status == SupplyOrder.Status.ORDERED
        task = SupplyReceivingTask.objects.get(pk=task_id)
        assert task.status == SupplyReceivingTask.Status.CREATED

    def test_direct_receive_forbidden(self):
        order_id, _, item_id = self._create_ordered_with_task()
        exp = (timezone.now().date() + timedelta(days=30)).isoformat()
        recv = self.client.post(
            f"/api/supply-orders/{order_id}/receive/",
            {"batches": [{"item_id": item_id, "expiration_date": exp}]},
            format="json",
        )
        assert recv.status_code == 403

    def test_complete_with_discrepancy(self):
        order_id, task_id, item_id = self._create_ordered_with_task()
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        mfg = self._manufacture_date()
        complete = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/",
            {
                "lines": [
                    {
                        "item_id": item_id,
                        "manufacture_date": mfg,
                        "actual_quantity": 8,
                        "discrepancy_note": "2 боя",
                    }
                ]
            },
            format="json",
        )
        assert complete.status_code == 200
        order = SupplyOrder.objects.get(pk=order_id)
        assert order.status == SupplyOrder.Status.RECEIVED
        assert order.has_discrepancies is True
        item = order.items.first()
        assert item.actual_quantity == 8
        assert item.discrepancy_note == "2 боя"
        batch = ProductBatch.objects.filter(supply_item=item).first()
        assert batch is not None
        assert batch.manufacture_date.isoformat() == mfg
        assert batch.expiration_date == timezone.now().date() - timedelta(days=2) + timedelta(
            days=30
        )

    def test_pool_employee_can_accept_unassigned(self):
        order_id, task_id, item_id = self._create_ordered_with_task()
        self.client.force_authenticate(self.employee)
        assert self.client.post(f"/api/receiving-tasks/{task_id}/accept/").status_code == 200
        mfg = self._manufacture_date()
        assert (
            self.client.post(
                f"/api/receiving-tasks/{task_id}/complete/",
                {
                    "lines": [
                        {
                            "item_id": item_id,
                            "manufacture_date": mfg,
                            "actual_quantity": 10,
                        }
                    ]
                },
                format="json",
            ).status_code
            == 200
        )

    def test_assigned_other_cannot_accept(self):
        _, task_id, _ = self._create_ordered_with_task(assigned_to=self.employee)
        self.client.force_authenticate(self.other)
        resp = self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        assert resp.status_code == 400

    def test_complete_twice_rejected(self):
        _, task_id, item_id = self._create_ordered_with_task()
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        mfg = self._manufacture_date()
        payload = {
            "lines": [
                {"item_id": item_id, "manufacture_date": mfg, "actual_quantity": 10}
            ]
        }
        self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/", payload, format="json"
        )
        again = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/", payload, format="json"
        )
        assert again.status_code == 400

    def test_draft_submit_via_endpoint(self):
        self.client.force_authenticate(self.admin)
        draft = self.client.post(
            "/api/supply-orders/",
            {
                "status": "draft",
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": 5,
                        "purchase_price": "10",
                    }
                ],
            },
            format="json",
        )
        order_id = draft.data["id"]
        submit = self.client.post(f"/api/supply-orders/{order_id}/submit/")
        assert submit.status_code == 200
        assert SupplyReceivingTask.objects.filter(supply_order_id=order_id).exists()

    def test_planned_receiving_date_on_create(self):
        planned = (timezone.now().date() + timedelta(days=7)).isoformat()
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/supply-orders/",
            {
                "status": "ordered",
                "planned_receiving_date": planned,
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": 3,
                        "purchase_price": "20.00",
                    }
                ],
            },
            format="json",
        )
        assert resp.status_code == 201
        order = SupplyOrder.objects.get(pk=resp.data["id"])
        assert order.planned_receiving_date.isoformat() == planned

    def test_submit_sets_planned_receiving_date(self):
        self.client.force_authenticate(self.admin)
        draft = self.client.post(
            "/api/supply-orders/",
            {
                "status": "draft",
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": 4,
                        "purchase_price": "15",
                    }
                ],
            },
            format="json",
        )
        order_id = draft.data["id"]
        planned = (timezone.now().date() + timedelta(days=3)).isoformat()
        submit = self.client.post(
            f"/api/supply-orders/{order_id}/submit/",
            {"planned_receiving_date": planned},
            format="json",
        )
        assert submit.status_code == 200
        order = SupplyOrder.objects.get(pk=order_id)
        assert order.planned_receiving_date.isoformat() == planned

    def test_complete_discrepancy_without_note_rejected(self):
        order_id, task_id, item_id = self._create_ordered_with_task()
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        mfg = self._manufacture_date()
        complete = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/",
            {
                "lines": [
                    {
                        "item_id": item_id,
                        "manufacture_date": mfg,
                        "actual_quantity": 7,
                    }
                ]
            },
            format="json",
        )
        assert complete.status_code == 400
        assert SupplyOrder.objects.get(pk=order_id).status == SupplyOrder.Status.ORDERED

    def test_complete_without_dates_for_non_expiring_product(self):
        apparel = Product.objects.create(
            name="Футболка",
            sku="TSH-REC",
            category=self.category,
            price=Decimal("500.00"),
            width=300,
            height=50,
            depth=250,
            weight=200,
            shelf_life_days=None,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/supply-orders/",
            {
                "status": "ordered",
                "items": [
                    {
                        "product": apparel.pk,
                        "quantity": 5,
                        "purchase_price": "200.00",
                    }
                ],
            },
            format="json",
        )
        order_id = resp.data["id"]
        item_id = resp.data["items"][0]["id"]
        task_id = SupplyReceivingTask.objects.get(supply_order_id=order_id).pk
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        complete = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/",
            {
                "lines": [
                    {
                        "item_id": item_id,
                        "actual_quantity": 5,
                    }
                ]
            },
            format="json",
        )
        assert complete.status_code == 200
        batch = ProductBatch.objects.filter(supply_item_id=item_id).first()
        assert batch is not None
        assert batch.manufacture_date is None
        assert batch.expiration_date == FAR_FUTURE_EXPIRY

    def test_complete_requires_manufacture_date_when_shelf_life_set(self):
        order_id, task_id, item_id = self._create_ordered_with_task()
        self.client.force_authenticate(self.employee)
        self.client.post(f"/api/receiving-tasks/{task_id}/accept/")
        complete = self.client.post(
            f"/api/receiving-tasks/{task_id}/complete/",
            {
                "lines": [
                    {
                        "item_id": item_id,
                        "actual_quantity": 10,
                    }
                ]
            },
            format="json",
        )
        assert complete.status_code == 400
        assert SupplyOrder.objects.get(pk=order_id).status == SupplyOrder.Status.ORDERED
