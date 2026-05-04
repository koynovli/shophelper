import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    Category,
    Company,
    Inventory,
    Product,
    ProductBatch,
    Store,
    SupplyOrder,
    SupplyOrderItem,
)


TEST_COMPANY_NAME = "Тестовая Компания"
TEST_STORE_NAME = "Тестовый Магазин"
TEST_CATEGORY_NAME = "Тестовая категория SCM"
MILK_SKU = "TEST-MILK-DOMIK-32"
MILK_NAME = "Молоко 'Домик в деревне' 3.2%"


class Command(BaseCommand):
    help = (
        "Создаёт тестовые данные для партионного учёта (FEFO): компания, магазин, "
        "заказ, три партии молока и остатки на складе."
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            self._cleanup()
            self._create()

        milk = Product.objects.get(sku=MILK_SKU)
        fefo_batch = (
            ProductBatch.objects.filter(
                product=milk,
                expiration_date__gte=timezone.now().date(),
            )
            .order_by("expiration_date")
            .first()
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Тестовые данные FEFO успешно созданы: компания, магазин, заказ, "
                "3 партии молока и 3 строки Inventory на складе."
            )
        )
        if fefo_batch is None:
            self.stdout.write(
                "FEFO (самая ранняя непросроченная партия): не найдено "
                "(все партии просрочены)."
            )
        else:
            self.stdout.write(
                "FEFO (самая ранняя непросроченная партия по expiration_date): "
                f"id={fefo_batch.pk}, store={fefo_batch.store_id}, "
                f"expiration_date={fefo_batch.expiration_date}, "
                f"current_quantity={fefo_batch.current_quantity}"
            )

    def _cleanup(self) -> None:
        # По ТЗ: удаление тестовой компании (каскадом снимаются заказы).
        Company.objects.filter(name=TEST_COMPANY_NAME).delete()
        # Дополнительно: старые партии/остатки/товар/магазин без FK на Company.
        Product.objects.filter(sku=MILK_SKU).delete()
        Store.objects.filter(name=TEST_STORE_NAME).delete()

    def _create(self) -> None:
        today = timezone.now().date()

        company = Company.objects.create(name=TEST_COMPANY_NAME)
        store = Store.objects.create(
            name=TEST_STORE_NAME,
            address="г. Москва, тестовый склад FEFO, ул. Примерная, 1",
        )
        category, _ = Category.objects.get_or_create(name=TEST_CATEGORY_NAME)
        milk = Product.objects.create(
            name=MILK_NAME,
            sku=MILK_SKU,
            gtin="04601234567890",
            category=category,
            price=Decimal("89.90"),
            width=round(random.uniform(55.0, 75.0), 1),
            height=round(random.uniform(180.0, 215.0), 1),
            depth=round(random.uniform(44.0, 58.0), 1),
            weight=round(random.uniform(980.0, 1050.0), 1),
            is_marked=True,
        )

        unit_price = Decimal("72.50")
        order = SupplyOrder.objects.create(
            company=company,
            store=store,
            status=SupplyOrder.Status.RECEIVED,
            received_at=timezone.now(),
            total_amount=Decimal("150") * unit_price,
            total_cost=Decimal("150") * unit_price,
        )
        order_item = SupplyOrderItem.objects.create(
            order=order,
            product=milk,
            quantity=150,
            actual_quantity=150,
            purchase_price=unit_price,
        )

        batches_spec = [
            ("Просрочка", today - timedelta(days=1), None),
            ("Горит", today + timedelta(days=1), None),
            ("Свежее", today + timedelta(days=10), "SN-DEMO-001"),
        ]
        batches = []
        for _, exp_date, serial in batches_spec:
            batch = ProductBatch.objects.create(
                product=milk,
                store=store,
                supply_item=order_item,
                purchase_price=unit_price,
                initial_quantity=50,
                current_quantity=50,
                manufacture_date=today - timedelta(days=30),
                expiration_date=exp_date,
                is_active=True,
                serial_number=serial,
            )
            batches.append(batch)

        for batch in batches:
            Inventory.objects.create(
                store=store,
                product=milk,
                batch=batch,
                quantity=50,
                status=Inventory.LocationStatus.WAREHOUSE,
            )
