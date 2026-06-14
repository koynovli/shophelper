from django.db import migrations, models
from django.db.models import Count


OPEN_PLACEMENT_STATUSES = ("CREATED", "PENDING", "IN_PROGRESS")


def merge_duplicate_open_placement_tasks(apps, schema_editor):
    PlacementTask = apps.get_model("core", "PlacementTask")
    duplicate_planograms = (
        PlacementTask.objects.filter(
            planogram_id__isnull=False,
            status__in=OPEN_PLACEMENT_STATUSES,
        )
        .values("planogram_id")
        .annotate(task_count=Count("id"))
        .filter(task_count__gt=1)
        .values_list("planogram_id", flat=True)
    )

    for planogram_id in duplicate_planograms:
        tasks = list(
            PlacementTask.objects.filter(
                planogram_id=planogram_id,
                status__in=OPEN_PLACEMENT_STATUSES,
            ).order_by("pk")
        )
        if len(tasks) <= 1:
            continue

        tasks.sort(
            key=lambda task: (
                0 if task.status == "IN_PROGRESS" else 1,
                task.pk,
            )
        )
        keeper = tasks[0]
        total_qty = sum(int(task.quantity) for task in tasks)
        batch_id = keeper.batch_id
        for task in tasks:
            if task.batch_id and batch_id is None:
                batch_id = task.batch_id

        for extra in tasks[1:]:
            extra.status = "CANCELLED"
            extra.save(update_fields=["status"])

        keeper.quantity = total_qty
        update_fields = ["quantity"]
        if keeper.batch_id is None and batch_id is not None:
            keeper.batch_id = batch_id
            update_fields.append("batch_id")
        keeper.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_placement_task_scan"),
    ]

    operations = [
        migrations.RunPython(
            merge_duplicate_open_placement_tasks,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="placementtask",
            name="uniq_placementtask_created_planogram",
        ),
        migrations.RemoveConstraint(
            model_name="shelfclearingtask",
            name="uniq_clearingtask_created_planogram",
        ),
        migrations.AddConstraint(
            model_name="placementtask",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("status__in", OPEN_PLACEMENT_STATUSES),
                ),
                fields=("planogram",),
                name="uniq_placementtask_open_planogram",
            ),
        ),
        migrations.AddConstraint(
            model_name="shelfclearingtask",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "CREATED")),
                fields=("slot",),
                name="uniq_clearingtask_created_slot",
            ),
        ),
    ]
