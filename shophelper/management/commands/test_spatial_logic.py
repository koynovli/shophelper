"""
Демонстрация пространственной логики: вместимость полки и отчёт о заполненности.

Данные магазина/молока — из setup_test_data (Тестовый Магазин, SKU тестового молока).
Габариты молока в БД хранятся в мм; в задании указаны см — переводим: 7×20×7 см → мм.
"""

from django.core.management.base import BaseCommand

from core.models import Equipment, Inventory, Product, Shelf, Store, Zone

TEST_STORE_NAME = "Тестовый Магазин"
MILK_SKU = "TEST-MILK-DOMIK-32"


def _shelf_fill_metrics(shelf: Shelf):
    """Та же логика, что в InventoryViewSet.shelf_fill_report (упрощённо для одной полки)."""
    inv_qs = Inventory.objects.filter(shelf=shelf).select_related("product")
    current_total = sum(inv.quantity for inv in inv_qs)

    caps_positive = []
    for inv in inv_qs:
        cap = shelf.calculate_max_capacity(inv.product)
        if cap > 0:
            caps_positive.append(cap)

    max_reference = max(caps_positive) if caps_positive else 0

    if max_reference > 0:
        fill_percent = min(
            100.0,
            round(current_total / max_reference * 100, 2),
        )
    else:
        fill_percent = None

    return current_total, max_reference, fill_percent


class Command(BaseCommand):
    help = (
        "Тестирует расчёт вместимости полки и процент заполнения (digital twin / Inventory)."
    )

    def handle(self, *args, **options):
        Zone.objects.all().delete()

        store = Store.objects.filter(name=TEST_STORE_NAME).first()
        milk = Product.objects.filter(sku=MILK_SKU).first()

        if store is None:
            self.stderr.write(
                self.style.ERROR(
                    f'Магазин "{TEST_STORE_NAME}" не найден. Запустите: '
                    "python manage.py setup_test_data"
                )
            )
            return

        if milk is None:
            self.stderr.write(
                self.style.ERROR(
                    f'Товар со SKU "{MILK_SKU}" не найден. Запустите setup_test_data.'
                )
            )
            return

        # В ТЗ: 7×20×7 см; в модели Product габариты в мм.
        milk.width = 70.0
        milk.height = 200.0
        milk.depth = 70.0
        milk.save(update_fields=["width", "height", "depth"])

        zone = Zone.objects.create(
            name="Молочный отдел",
            store=store,
            color="#E8F4FC",
        )

        rack = Equipment.objects.create(
            name="Стеллаж пристенный №1",
            zone=zone,
            type=Equipment.EquipmentType.SHELF,
            pos_x=10.5,
            pos_y=20.0,
            width=100.0,
            height=200.0,
            orientation=0.0,
        )

        shelf1 = Shelf.objects.create(
            equipment=rack,
            level=1,
            width=100.0,
            depth=60.0,
            height=40.0,
        )
        Shelf.objects.create(
            equipment=rack,
            level=2,
            width=100.0,
            depth=40.0,
            height=30.0,
        )
        # Третья полка — параметры в ТЗ не даны; задаём компактный верхний ярус.
        Shelf.objects.create(
            equipment=rack,
            level=3,
            width=100.0,
            depth=35.0,
            height=25.0,
        )

        max_units = shelf1.calculate_max_capacity(milk)
        self.stdout.write(
            self.style.SUCCESS(
                f"calculate_max_capacity (полка 1, нижняя): {max_units} шт."
            )
        )

        Inventory.objects.update_or_create(
            store=store,
            product=milk,
            batch=None,
            defaults={
                "quantity": 20,
                "shelf": shelf1,
                "status": Inventory.LocationStatus.SHELF,
            },
        )

        current_total, max_reference, fill_percent = _shelf_fill_metrics(shelf1)

        pct_str = f"{fill_percent}%" if fill_percent is not None else "н/д"

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"На полку вмещается {max_reference} штук, "
                f"сейчас там {current_total} штук, "
                f"заполнено на {pct_str} "
                f"(та же логика, что в GET /api/inventory/shelf_fill_report/)."
            )
        )
