"""Сбрасывает завышенные целевые веса в планограммах (ошибка bulk-автозаполнения)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.models import Planogram, Product
from core.product_units import MAX_BOX_PLANOGRAM_TARGET_KG, kg_to_grams
from core.spatial_engine import refresh_slot_max_capacity


class Command(BaseCommand):
    help = (
        "Находит планограммы весовых товаров с target_quantity выше допустимого "
        f"({MAX_BOX_PLANOGRAM_TARGET_KG} кг) и при --apply сбрасывает max_capacity слота."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Удалить планограммы с завышенным целевым весом (слот нужно заполнить заново).",
        )

    def handle(self, *args, **options):
        max_grams = kg_to_grams(MAX_BOX_PLANOGRAM_TARGET_KG)
        qs = (
            Planogram.objects.filter(product__sale_unit=Product.SaleUnit.WEIGHT)
            .filter(target_quantity__gt=max_grams)
            .select_related("slot", "product")
        )
        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Завышенных планограмм не найдено."))
            return

        for pg in qs:
            kg = int(pg.target_quantity or 0) / 1000
            self.stdout.write(
                f"  planogram={pg.pk} product={pg.product.name!r} "
                f"target={pg.target_quantity} g ({kg} kg) slot={pg.slot_id}"
            )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Найдено {count} планограмм. Запустите с --apply, чтобы удалить их "
                    "и затем задайте целевой вес вручную в мерчандайзинге."
                )
            )
            return

        for pg in qs:
            slot = pg.slot
            product_name = pg.product.name
            pg.delete()
            refresh_slot_max_capacity(slot)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Удалена planogram для {product_name!r} (slot {slot.pk})."
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Обработано планограмм: {count}."))
