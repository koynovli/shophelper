from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    Category,
    Equipment,
    PlacementTask,
    Planogram,
    Product,
    ProductBatch,
    StockItem,
    Store,
    Zone,
)

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

    def test_create_product_with_shelf_life_days(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/products/",
            {**self.payload, "shelf_life_days": 14},
            format="json",
        )
        assert resp.status_code == 201
        product = Product.objects.get(sku="KEFIR-1")
        assert product.shelf_life_days == 14

    def test_patch_shelf_life_days(self):
        self.client.force_authenticate(self.admin)
        create = self.client.post("/api/products/", self.payload, format="json")
        assert create.status_code == 201
        product = Product.objects.get(sku="KEFIR-1")
        patch = self.client.patch(
            f"/api/products/{product.pk}/",
            {"shelf_life_days": 21},
            format="json",
        )
        assert patch.status_code == 200
        product.refresh_from_db()
        assert product.shelf_life_days == 21

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

    def test_admin_patch_product(self):
        product = Product.objects.create(
            name="Молоко",
            sku="MILK-PATCH",
            category=self.category,
            price=Decimal("50"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            f"/api/products/{product.pk}/",
            {"name": "Молоко 2.5%", "price": "65.00"},
            format="json",
        )
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.name == "Молоко 2.5%"
        assert Decimal(str(product.price)) == Decimal("65.00")

    def test_employee_cannot_patch_product(self):
        product = Product.objects.create(
            name="Хлеб",
            sku="BREAD-1",
            category=self.category,
            price=Decimal("40"),
            width=50,
            height=100,
            depth=50,
            weight=300,
        )
        self.client.force_authenticate(self.employee)
        resp = self.client.patch(
            f"/api/products/{product.pk}/",
            {"name": "Булка"},
            format="json",
        )
        assert resp.status_code == 403

    def test_admin_delete_product_without_links(self):
        product = Product.objects.create(
            name="Вода",
            sku="WATER-DEL",
            category=self.category,
            price=Decimal("30"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 204
        assert not Product.objects.filter(pk=product.pk).exists()

    def test_delete_blocked_by_stock(self):
        store = Store.objects.create(name="S", address="A")
        product = Product.objects.create(
            name="Сыр",
            sku="CHEESE-1",
            category=self.category,
            price=Decimal("200"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        ProductBatch.objects.create(
            product=product,
            store=store,
            initial_quantity=10,
            current_quantity=0,
            expiration_date=date.today() + timedelta(days=5),
            purchase_price="150.00",
            is_active=False,
        )
        StockItem.objects.filter(product=product).update(quantity=5)
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 400
        assert "удалить" in str(resp.data).lower()
        assert "склад" in str(resp.data).lower()

    def test_delete_allowed_with_orphan_stock_item(self):
        product = Product.objects.create(
            name="Тестовый товар (legacy)",
            sku="TEST-PL-legacy",
            category=self.category,
            price=Decimal("1"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        StockItem.objects.create(product=product, quantity=24)
        self.client.force_authenticate(self.admin)
        info = self.client.get(f"/api/products/{product.pk}/delete-info/")
        assert info.status_code == 200
        assert info.data["can_delete"] is True
        assert info.data["blockers"] == []
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 204
        assert not Product.objects.filter(pk=product.pk).exists()
        assert not StockItem.objects.filter(product=product).exists()

    def test_delete_blocked_by_planogram(self):
        store = Store.objects.create(name="S", address="A")
        zone = Zone.objects.create(name="Z", store=store, color="#000")
        equipment = Equipment.objects.create(
            name="Rack",
            zone=zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=1,
        )
        slot = equipment.slots.first()
        product = Product.objects.create(
            name="Йогурт",
            sku="YOG-1",
            category=self.category,
            price=Decimal("55"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        Planogram.objects.create(slot=slot, product=product, target_quantity=3)
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 400
        assert "планограмм" in str(resp.data).lower()

    def test_delete_allowed_with_depleted_batch(self):
        store = Store.objects.create(name="S", address="A")
        product = Product.objects.create(
            name="Сок",
            sku="JUICE-0",
            category=self.category,
            price=Decimal("40"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        ProductBatch.objects.create(
            product=product,
            store=store,
            initial_quantity=10,
            current_quantity=0,
            expiration_date=date.today() + timedelta(days=5),
            purchase_price="30.00",
            is_active=False,
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 204
        assert not Product.objects.filter(pk=product.pk).exists()

    def test_delete_blocked_by_batch_with_stock(self):
        store = Store.objects.create(name="S2", address="A")
        product = Product.objects.create(
            name="Сок 2",
            sku="JUICE-1",
            category=self.category,
            price=Decimal("40"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        ProductBatch.objects.create(
            product=product,
            store=store,
            initial_quantity=10,
            current_quantity=3,
            expiration_date=date.today() + timedelta(days=5),
            purchase_price="30.00",
        )
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 400
        assert "партии" in str(resp.data).lower()

    def test_delete_allowed_with_completed_placement_only(self):
        store = Store.objects.create(name="S3", address="A")
        zone = Zone.objects.create(name="Z", store=store, color="#000")
        equipment = Equipment.objects.create(
            name="Rack",
            zone=zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=1,
        )
        slot = equipment.slots.first()
        product = Product.objects.create(
            name="Чай",
            sku="TEA-1",
            category=self.category,
            price=Decimal("80"),
            width=50,
            height=100,
            depth=50,
            weight=200,
        )
        planogram = Planogram.objects.create(slot=slot, product=product, target_quantity=2)
        PlacementTask.objects.create(
            planogram=planogram,
            product=product,
            equipment=equipment,
            quantity=2,
            status=PlacementTask.Status.COMPLETED,
        )
        planogram.delete()
        self.client.force_authenticate(self.admin)
        info = self.client.get(f"/api/products/{product.pk}/delete-info/")
        assert info.status_code == 200
        assert info.data["can_delete"] is True
        assert len(info.data["warnings"]) >= 1
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 204

    def test_delete_blocked_by_active_placement_task(self):
        store = Store.objects.create(name="S4", address="A")
        zone = Zone.objects.create(name="Z2", store=store, color="#000")
        equipment = Equipment.objects.create(
            name="Fridge",
            zone=zone,
            type=Equipment.EquipmentType.FRIDGE,
            pos_x=0,
            pos_y=0,
            width=100,
            height=60,
            rows_count=1,
        )
        slot = equipment.slots.first()
        product = Product.objects.create(
            name="Кефир",
            sku="KEFIR-DEL",
            category=self.category,
            price=Decimal("55"),
            width=50,
            height=100,
            depth=50,
            weight=500,
        )
        planogram = Planogram.objects.create(slot=slot, product=product, target_quantity=3)
        PlacementTask.objects.create(
            planogram=planogram,
            product=product,
            equipment=equipment,
            quantity=2,
            status=PlacementTask.Status.CREATED,
        )
        self.client.force_authenticate(self.admin)
        info = self.client.get(f"/api/products/{product.pk}/delete-info/")
        assert info.status_code == 200
        assert info.data["can_delete"] is False
        assert any("планограмм" in b for b in info.data["blockers"])
        resp = self.client.delete(f"/api/products/{product.pk}/")
        assert resp.status_code == 400
