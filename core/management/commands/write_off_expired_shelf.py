from django.core.management.base import BaseCommand

from core.expiry_writeoff import write_off_expired_shelf_stock


class Command(BaseCommand):
    help = (
        "Списать просроченный товар с полок (партия последней COMPLETED-выкладки на слот)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--store-id",
            type=int,
            default=None,
            help="Ограничить одним магазином",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только отчёт, без изменений в БД",
        )

    def handle(self, *args, **options):
        store_id = options.get("store_id")
        dry_run = bool(options.get("dry_run"))
        result = write_off_expired_shelf_stock(store_id=store_id, dry_run=dry_run)

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Списано слотов: {result.slots_written_off}, "
                f"единиц: {result.units_written_off}"
            )
        )
        for entry in result.entries:
            self.stdout.write(
                f"  planogram={entry.planogram_id} slot={entry.slot_id} "
                f"product={entry.product_id} batch={entry.batch_id} qty={entry.quantity}"
            )
