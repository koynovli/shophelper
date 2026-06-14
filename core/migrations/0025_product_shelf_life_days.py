from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_equipment_row_slot_layouts"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="shelf_life_days",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="От даты производства. Пусто — контроль срока не ведётся.",
                null=True,
                verbose_name="Срок годности (дней)",
            ),
        ),
    ]
