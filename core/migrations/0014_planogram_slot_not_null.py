from django.db import migrations, models
import django.db.models.deletion


def assert_no_null_slots(apps, schema_editor):
    Planogram = apps.get_model("core", "Planogram")
    null_count = Planogram.objects.filter(slot__isnull=True).count()
    if null_count:
        raise RuntimeError(
            f"Нельзя сделать Planogram.slot обязательным: найдено записей с NULL slot: {null_count}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_equipment_slots_and_planogram_slots"),
    ]

    operations = [
        migrations.RunPython(assert_no_null_slots, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="planogram",
            name="slot",
            field=models.ForeignKey(
                help_text="Слот на оборудовании, куда должен выкладываться товар.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="planograms",
                to="core.equipmentslot",
                verbose_name="Слот",
            ),
        ),
    ]
