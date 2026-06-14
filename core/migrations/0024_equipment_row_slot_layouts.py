from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_equipment_slot_profiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipment",
            name="row_slot_layouts",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    'Список по рядам: [{"slot_count": N, "widths": [..]}]. '
                    "Пусто — стандартная сетка профиля."
                ),
                verbose_name="Разбивка рядов на слоты",
            ),
        ),
    ]
