from django.core.management.base import BaseCommand

from core.write_off_service import scan_expired_write_off_tasks


class Command(BaseCommand):
    help = (
        "Сканирует просрочку на складе и полках и создаёт задания на списание сотрудникам."
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
            help="Только отчёт, без создания заданий",
        )

    def handle(self, *args, **options):
        store_id = options.get("store_id")
        dry_run = bool(options.get("dry_run"))
        result = scan_expired_write_off_tasks(store_id, dry_run=dry_run)

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Заданий: {result.tasks_total} "
                f"(склад: {result.warehouse_tasks}, полки: {result.shelf_tasks}), "
                f"единиц: {result.warehouse_units + result.shelf_units}"
            )
        )
