from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Category, Product, StockItem

User = get_user_model()


class ProductCatalogApiTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Напитки")
        self.admin = User.objects.create_user(
            username="admin_cat",
            password="pass",
            role=User.Role.ADMIN,
        )
        self.employee = User.objects.create_user(
            username="emp_cat",
            password="pass",
            role=User.Role.EMPLOYEE,
        )
        self.client = APIClient()
        self.payload = {
            "name": "Кефир 1%",
            "sku": "KEFIR-1",
            "category": self.category.pk,
            "price": "89.90",
            "width": 60,
            "height": 120,
            "depth": 60,
            "weight": 450,
            "is_marked": False,
            "is_stackable": True,
        }

    def test_admin_create_product_no_stock_item(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/products/", self.payload, format="json")
        assert resp.status_code == 201
        product = Product.objects.get(sku="KEFIR-1")
        assert product.name == "Кефир 1%"
        assert product.category_id == self.category.pk
        assert Decimal(str(product.price)) == Decimal("89.90")
        assert not StockItem.objects.filter(product=product).exists()

    def test_employee_cannot_create_product(self):
        self.client.force_authenticate(self.employee)
        resp = self.client.post("/api/products/", self.payload, format="json")
        assert resp.status_code == 403

    def test_duplicate_sku_rejected(self):
        Product.objects.create(
            name="Existing",
            sku="KEFIR-1",
            category=self.category,
            price=Decimal("1"),
            width=10,
            height=10,
            depth=10,
            weight=10,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/products/", self.payload, format="json")
        assert resp.status_code == 400

    def test_create_category_and_product(self):
        self.client.force_authenticate(self.admin)
        cat_resp = self.client.post(
            "/api/categories/",
            {"name": "Молочные"},
            format="json",
        )
        assert cat_resp.status_code == 201
        cat_id = cat_resp.data["id"]
        payload = {**self.payload, "sku": "MILK-2", "category": cat_id}
        prod_resp = self.client.post("/api/products/", payload, format="json")
        assert prod_resp.status_code == 201
        assert Product.objects.filter(sku="MILK-2", category_id=cat_id).exists()

    def test_list_returns_extended_fields(self):
        Product.objects.create(
            name="Молоко",
            sku="MILK-1",
            category=self.category,
            price=Decimal("50"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.client.force_authenticate(self.employee)
        resp = self.client.get("/api/products/")
        assert resp.status_code == 200
        row = resp.data[0] if isinstance(resp.data, list) else resp.data["results"][0]
        assert "category" in row
        assert row["width"] == 50
