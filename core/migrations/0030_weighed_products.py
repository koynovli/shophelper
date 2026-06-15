from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_task_slot_sync_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="sale_unit",
            field=models.CharField(
                choices=[("piece", "Штучный"), ("weight", "На развес")],
                default="piece",
                help_text="Штучный товар или на развес (учёт в граммах).",
                max_length=10,
                verbose_name="Единица продажи",
            ),
        ),
        migrations.AddField(
            model_name="placementtaskscan",
            name="weight_grams",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Для товаров на развес — вес отсканированной порции в граммах.",
                null=True,
                verbose_name="Вес скана (г)",
            ),
        ),
    ]
