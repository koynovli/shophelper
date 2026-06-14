from django.core.management.base import BaseCommand

from core.models import Product, ProductBatch, StockItem
from core.placement_sync import sync_stock_item_from_batches


class Command(BaseCommand):
    help = "Пересчитать StockItem.quantity по активным непросроченным партиям (FEFO)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--product-id",
            type=int,
            default=None,
            help="Ограничить одним товаром",
        )

    def handle(self, *args, **options):
        product_id = options.get("product_id")
        if product_id is not None:
            product_ids = [product_id]
        else:
            batch_ids = ProductBatch.objects.values_list("product_id", flat=True).distinct()
            stock_ids = StockItem.objects.values_list("product_id", flat=True).distinct()
            product_ids = sorted(set(batch_ids) | set(stock_ids))

        updated = 0
        for pid in product_ids:
            if not Product.objects.filter(pk=pid).exists():
                continue
            before = StockItem.objects.filter(product_id=pid).values_list("quantity", flat=True).first()
            after = sync_stock_item_from_batches(pid)
            if before is None or int(before) != after:
                updated += 1
                self.stdout.write(f"product={pid}: {before or 0} -> {after}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Синхронизировано товаров: {updated} из {len(product_ids)}"
            )
        )
