from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_weighed_products"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="supplyorder",
            name="cancellation_reason_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("manager_changed_mind", "Управляющий передумал"),
                    ("supplier_unable", "Поставщик не смог поставить"),
                    ("order_error", "Ошибка в заказе"),
                    ("other", "Другое"),
                ],
                default="",
                help_text="Код причины отмены заказа.",
                max_length=40,
                verbose_name="Причина отмены",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="cancellation_reason_note",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Дополнительный комментарий при отмене заказа.",
                verbose_name="Комментарий к отмене",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="cancelled_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Дата и время отмены заказа.",
                null=True,
                verbose_name="Отменён",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                help_text="Пользователь, отменивший заказ.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_supply_orders",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Кем отменён",
            ),
        ),
    ]
