import math
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Store(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Название магазина.",
    )
    address = models.CharField(
        max_length=500,
        verbose_name="Адрес",
        help_text="Фактический адрес магазина.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата и время создания записи магазина.",
    )

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Магазины"

    def __str__(self) -> str:
        return self.name


class StoreMap(models.Model):
    """Границы интерактивной 2D-карты торгового зала (в метрах)."""

    store = models.OneToOneField(
        Store,
        on_delete=models.CASCADE,
        related_name="floor_map",
        verbose_name="Магазин",
    )
    width_m = models.FloatField(
        default=20.0,
        verbose_name="Ширина зала (м)",
        help_text="Ширина торгового зала на плане в метрах.",
    )
    length_m = models.FloatField(
        default=15.0,
        verbose_name="Длина зала (м)",
        help_text="Длина торгового зала на плане в метрах.",
    )

    class Meta:
        verbose_name = "План зала"
        verbose_name_plural = "Планы зала"

    def __str__(self) -> str:
        return f"План {self.store} ({self.width_m}×{self.length_m} м)"


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        EMPLOYEE = "employee", "Работник торгового зала"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        verbose_name="Роль",
        help_text="Роль пользователя в системе.",
    )
    phone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        verbose_name="Телефон",
        help_text="Контактный номер телефона пользователя.",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="Магазин",
        help_text="Магазин, к которому привязан пользователь (если применимо).",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_merchandiser(self) -> bool:
        return self.role == self.Role.EMPLOYEE

    def __str__(self) -> str:
        full_name = self.get_full_name().strip()
        return full_name or self.username


class Category(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название",
        help_text="Название категории товаров.",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Название товара.",
    )
    sku = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="SKU",
        help_text="Артикул (SKU) товара.",
    )
    gtin = models.CharField(
        max_length=14,
        unique=True,
        null=True,
        blank=True,
        verbose_name="GTIN",
        help_text="Глобальный номер товарной единицы (14 цифр), маркировка Честный ЗНАК / GS1.",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Категория",
        help_text="Категория, к которой относится товар.",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Цена",
        help_text="Цена товара (в валюте проекта).",
    )
    image = models.ImageField(
        upload_to="products/",
        null=True,
        blank=True,
        verbose_name="Изображение",
        help_text="Изображение товара.",
    )
    width = models.FloatField(
        verbose_name="Ширина (мм)",
        help_text="Ширина товара в миллиметрах.",
    )
    height = models.FloatField(
        verbose_name="Высота (мм)",
        help_text="Высота товара в миллиметрах.",
    )
    depth = models.FloatField(
        verbose_name="Глубина (мм)",
        help_text="Глубина товара в миллиметрах.",
    )
    weight = models.FloatField(
        verbose_name="Вес",
        help_text="Вес товара (единица измерения по договорённости, например граммы).",
    )
    is_marked = models.BooleanField(
        default=False,
        verbose_name="Маркированный товар",
        help_text="Товар с обязательной маркировкой (например, «Честный ЗНАК»).",
    )
    is_stackable = models.BooleanField(
        default=True,
        verbose_name="Можно штабелировать",
        help_text="Если False — на полке только один ярус по высоте.",
    )
    allowed_equipment_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Допустимые типы оборудования",
        help_text="Пустой список — без ограничения. Иначе whitelist типов выкладки.",
    )
    shelf_life_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Срок годности (дней)",
        help_text="От даты производства. Пусто — контроль срока не ведётся.",
    )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class Company(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Наименование организации (тенанта / юрлица).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
        help_text="Дата и время создания записи в системе.",
    )

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"

    def __str__(self) -> str:
        return self.name


class Supplier(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Наименование поставщика.",
    )
    contact_info = models.TextField(
        blank=True,
        verbose_name="Контактные данные",
        help_text="Телефон, e-mail, адрес и другие контакты.",
    )
    inn = models.CharField(
        max_length=12,
        verbose_name="ИНН",
        help_text="Идентификационный номер налогоплательщика (ИНН).",
    )

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"

    def __str__(self) -> str:
        return self.name


class Inventory(models.Model):
    class LocationStatus(models.TextChoices):
        ORDERED = "ordered", "Заказано"
        WAREHOUSE = "warehouse", "На складе"
        SHELF = "shelf", "На витрине"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="inventories",
        verbose_name="Магазин",
        help_text="Торговая точка, где отражаются остатки.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventories",
        verbose_name="Товар",
        help_text="Товарный SKU.",
    )
    batch = models.ForeignKey(
        "ProductBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_lines",
        verbose_name="Партия",
        help_text="Партия, из которой образован этот остаток (FEFO/FIFO, полка/склад).",
    )
    shelf = models.ForeignKey(
        "Shelf",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventories",
        verbose_name="Полка (план зала)",
        help_text="Приоритетная привязка к полке цифрового двойника зала (если указана).",
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество",
        help_text="Количество единиц товара по данной записи.",
    )
    status = models.CharField(
        max_length=20,
        choices=LocationStatus.choices,
        default=LocationStatus.WAREHOUSE,
        verbose_name="Статус нахождения",
        help_text="Где физически учитывается товар; при заполненной полке «shelf» "
        "местоположение в первую очередь определяется по цифровому плану зала.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
        help_text="Время последнего изменения записи.",
    )

    class Meta:
        verbose_name = "Остаток"
        verbose_name_plural = "Остатки"
        constraints = [
            models.UniqueConstraint(
                fields=["store", "product"],
                condition=models.Q(batch__isnull=True),
                name="uniq_inventory_store_product_no_batch",
            ),
            models.UniqueConstraint(
                fields=["store", "product", "batch"],
                condition=models.Q(batch__isnull=False),
                name="uniq_inventory_store_product_batch",
            ),
        ]

    def __str__(self) -> str:
        batch_hint = f", партия {self.batch_id}" if self.batch_id else ""
        return f"{self.store} — {self.product} ({self.quantity}{batch_hint})"


class SupplyOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ORDERED = "ordered", "В пути"
        RECEIVED = "received", "Принят"
        CANCELLED = "cancelled", "Отменен"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="supply_orders",
        verbose_name="Организация",
        help_text="Организация-заказчик поставки.",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="supply_orders",
        verbose_name="Магазин",
        help_text="Магазин назначения: куда везут товар.",
    )
    supplier = models.ForeignKey(
        "Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_orders",
        verbose_name="Поставщик",
        help_text="Поставщик по договору (если указан).",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Статус",
        help_text="Этап жизненного цикла заказа поставщику.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
        help_text="Дата и время создания заказа.",
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Принят",
        help_text="Время фактической приёмки по складу/магазину.",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Сумма закупки",
        help_text="Итоговая сумма заказа (валюта проекта; может совпадать с суммой позиций).",
    )
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Общая стоимость закупки",
        help_text="Фактическая сумма при приёмке: Σ (факт × закупочная цена по строке).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supply_orders",
        verbose_name="Кем создан",
        help_text="Пользователь, оформивший заказ.",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_supply_orders",
        verbose_name="Кем принят",
        help_text="Пользователь, зафиксировавший приёмку на складе/в магазине.",
    )
    has_discrepancies = models.BooleanField(
        default=False,
        verbose_name="Есть расхождения",
        help_text="Фактическое количество хотя бы по одной строке отличается от заказанного.",
    )
    planned_receiving_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Плановая дата приёмки",
        help_text="Ожидаемая дата поступления товара на склад (план менеджера).",
    )

    class Meta:
        verbose_name = "Заказ поставщику"
        verbose_name_plural = "Заказы поставщикам"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Заказ #{self.pk or '—'} — {self.store} ({self.get_status_display()})"

    def mark_as_received(self) -> None:
        # TODO: Логика создания ProductBatch и обновления Inventory будет в API-слое
        self.status = self.Status.RECEIVED
        self.received_at = timezone.now()
        self.save(update_fields=["status", "received_at"])


class SupplyOrderItem(models.Model):
    order = models.ForeignKey(
        SupplyOrder,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ",
        help_text="Заказ поставщику, к которому относится строка.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="supply_order_items",
        verbose_name="Товар",
        help_text="Товар в строке заказа.",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="Ожидаемое количество",
        help_text="Заказанное количество единиц по строке.",
    )
    actual_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Фактическое количество",
        help_text="Фактически принятое количество (заполняется при приёмке).",
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Цена закупки за единицу",
        help_text="Закупочная цена за единицу товара в этой строке.",
    )
    discrepancy_note = models.TextField(
        blank=True,
        verbose_name="Примечание по расхождению",
        help_text="Комментарий сотрудника, если факт ≠ заказ.",
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity} (заказ {self.order_id})"


class SupplyReceivingTask(models.Model):
    """Задача приёмки заказа поставщику на склад (исполняет сотрудник)."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Создана"
        IN_PROGRESS = "IN_PROGRESS", "Выполняется"
        COMPLETED = "COMPLETED", "Завершена"
        CANCELLED = "CANCELLED", "Отменена"

    supply_order = models.OneToOneField(
        SupplyOrder,
        on_delete=models.CASCADE,
        related_name="receiving_task",
        verbose_name="Заказ поставщику",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="Статус",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_receiving_tasks",
        verbose_name="Исполнитель",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supply_receiving_tasks",
        verbose_name="Кем создана",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершена",
    )

    class Meta:
        verbose_name = "Задача приёмки заказа"
        verbose_name_plural = "Задачи приёмки заказов"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Приёмка заказа #{self.supply_order_id} ({self.status})"


class ProductBatch(models.Model):
    """Партия товара с партионным учётом и сроком годности (FEFO)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name="Товар",
        help_text="Номенклатура в партии.",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="product_batches",
        verbose_name="Магазин",
        help_text="Точка, где учитывается остаток партии.",
    )
    supply_item = models.ForeignKey(
        SupplyOrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
        verbose_name="Позиция заказа поставки",
        help_text="Строка заказа поставщику, по которой оприходована партия (если применимо).",
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Закупочная цена",
        help_text="Себестоимость единицы в рамках этой партии.",
    )
    initial_quantity = models.PositiveIntegerField(
        verbose_name="Начальное количество",
        help_text="Количество при первичной приёмке в партию.",
    )
    current_quantity = models.PositiveIntegerField(
        verbose_name="Текущее количество в партии",
        help_text="Остаток по партии с учётом списаний и перемещений.",
    )
    manufacture_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата производства",
        help_text="Дата выпуска (если есть на маркировке).",
    )
    expiration_date = models.DateField(
        verbose_name="Срок годности",
        help_text="Крайняя дата годности; обязательна для контроля FEFO.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
        help_text="Неактивные партии исключаются из подбора под новые операции.",
    )
    serial_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Серийный номер",
        help_text="Идентификатор единицы маркированного товара (AI 21 в Data Matrix).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
        help_text="Запись партии в системе.",
    )

    class Meta:
        verbose_name = "Партия товара"
        verbose_name_plural = "Партии товаров"
        ordering = ("expiration_date", "pk")

    def __str__(self) -> str:
        return f"{self.product.sku} @ {self.store} -> до {self.expiration_date}"

    def get_remaining_days(self) -> int:
        """Возвращает число дней до окончания срока годности (отрицательное — просрочка)."""
        today = timezone.localdate()
        return (self.expiration_date - today).days

    @property
    def is_expired(self) -> bool:
        return self.expiration_date < timezone.localdate()

    def deduct_quantity(self, amount: int) -> None:
        """Уменьшает остаток партии; при нуле помечает партию неактивной."""
        if amount < 1:
            raise ValueError("Количество для списания должно быть не меньше 1.")
        if amount > self.current_quantity:
            raise ValueError("Нельзя списать больше, чем текущий остаток партии.")
        self.current_quantity -= amount
        if self.current_quantity == 0:
            self.is_active = False
        self.save(update_fields=["current_quantity", "is_active"])


class Zone(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text='Например: «Торговый зал», «Склад».',
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="zones",
        verbose_name="Магазин",
        help_text="Магазин, к которому относится зона на плане.",
    )
    color = models.CharField(
        max_length=32,
        verbose_name="Цвет на карте",
        help_text="Цвет отображения зоны (например, HEX-код #RRGGBB).",
    )

    class Meta:
        verbose_name = "Зона"
        verbose_name_plural = "Зоны"

    def __str__(self) -> str:
        return f"{self.name} ({self.store})"


class Equipment(models.Model):
    """Оборудование на плане зала (цифровой двойник)."""

    class EquipmentType(models.TextChoices):
        SHELF = "shelf", "Стеллаж"
        HANGER = "hanger", "Вешалка"
        FRIDGE = "fridge", "Холодильник"
        BOX = "box", "Бокс / корзина"
        MANNEQUIN = "mannequin", "Манекен / промо-стенд"

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text='Например: «Стеллаж №1».',
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.CASCADE,
        related_name="equipment",
        verbose_name="Зона",
        help_text="Зона торгового зала или склада, где стоит объект.",
    )
    type = models.CharField(
        max_length=20,
        choices=EquipmentType.choices,
        default=EquipmentType.SHELF,
        verbose_name="Тип",
        help_text="Тип оборудования для отрисовки и логики.",
    )
    pos_x = models.FloatField(
        verbose_name="Позиция X (центр)",
        help_text="Координата X центра объекта на плане.",
    )
    pos_y = models.FloatField(
        verbose_name="Позиция Y (центр)",
        help_text="Координата Y центра объекта на плане.",
    )
    width = models.FloatField(
        verbose_name="Ширина",
        help_text="Ширина объекта на плане (условные единицы или см — по договорённости).",
    )
    height = models.FloatField(
        verbose_name="Высота",
        help_text="Высота объекта на плане (условные единицы или см — по договорённости).",
    )
    rotation = models.FloatField(
        default=0.0,
        verbose_name="Поворот (°)",
        help_text="Угол поворота объекта на плане в градусах.",
    )
    rows_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Число рядов/уровней",
        help_text=(
            "Количество уровней для визуализации и слотов: для стеллажа — полки, "
            "для перфопанели — ряды крючков, для паллеты обычно 1."
        ),
    )
    row_slot_layouts = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Разбивка рядов на слоты",
        help_text=(
            "Список по рядам: [{\"slot_count\": N, \"widths\": [..]}]. "
            "Пусто — стандартная сетка профиля."
        ),
    )

    class Meta:
        verbose_name = "Оборудование (план зала)"
        verbose_name_plural = "Оборудование (план зала)"

    def __str__(self) -> str:
        return f"{self.name} — {self.zone}"


class EquipmentSlot(models.Model):
    """Ячейка (слот) на конкретном оборудовании, куда привязывается планограмма."""

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="slots",
        verbose_name="Оборудование",
    )
    row_index = models.PositiveIntegerField(
        verbose_name="Индекс ряда",
        help_text="Номер полки/ряда, начиная с 0.",
    )
    col_index = models.PositiveIntegerField(
        verbose_name="Индекс ячейки",
        help_text="Порядковый номер ячейки в ряду, начиная с 0.",
    )
    width_percent = models.FloatField(
        default=25.0,
        verbose_name="Ширина (%)",
        help_text="Ширина ячейки в процентах от ширины ряда/полки.",
    )
    slot_label = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Подпись зоны",
        help_text="Например: «Верх» для зоны экспозиции на манекене.",
    )
    qr_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="QR-токен",
        help_text="UUID для QR-кода полки; сканируется при верификации выкладки.",
    )
    shelf = models.ForeignKey(
        "Shelf",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_slots",
        verbose_name="Физическая полка",
        help_text="Полка с габаритами для расчёта вместимости; если пусто — по row_index.",
    )
    current_qty = models.PositiveIntegerField(
        default=0,
        verbose_name="Текущий остаток на полке",
        help_text="Сколько единиц товара сейчас на слоте (витрина).",
    )
    max_capacity = models.PositiveIntegerField(
        default=0,
        verbose_name="Макс. вместимость",
        help_text="Рассчитанная вместимость слота для SKU планограммы.",
    )

    class Meta:
        verbose_name = "Слот оборудования"
        verbose_name_plural = "Слоты оборудования"
        ordering = ("equipment_id", "row_index", "col_index")
        constraints = [
            models.UniqueConstraint(
                fields=("equipment", "row_index", "col_index"),
                name="uniq_equipment_slot_row_col",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.equipment.name}: ряд {self.row_index}, ячейка {self.col_index}"

    def refresh_max_capacity_for_product(self, product: "Product") -> int:
        from .spatial_engine import refresh_slot_max_capacity

        return refresh_slot_max_capacity(self, product)


class Planogram(models.Model):
    """Планограмма торгового зала: целевое количество SKU в конкретном слоте."""

    slot = models.ForeignKey(
        EquipmentSlot,
        on_delete=models.CASCADE,
        related_name="planograms",
        verbose_name="Слот",
        help_text="Слот на оборудовании, куда должен выкладываться товар.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="floor_planograms",
        verbose_name="Товар",
        help_text="Товар, который должен быть представлен на этом оборудовании.",
    )
    target_quantity = models.PositiveIntegerField(
        verbose_name="Целевое количество",
        help_text="Сколько единиц товара должно находиться на полке в идеале.",
    )

    class Meta:
        verbose_name = "Планограмма (зал)"
        verbose_name_plural = "Планограммы (зал)"
        constraints = [
            models.UniqueConstraint(
                fields=("slot", "product"),
                name="uniq_planogram_slot_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.slot.equipment.name} [{self.slot.row_index}:{self.slot.col_index}]: {self.product.name} → {self.target_quantity} шт."


class StockItem(models.Model):
    """Агрегированный остаток на складе магазина по товару (для сопоставления с планограммой)."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_item",
        verbose_name="Товар",
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество на складе",
        help_text="Сколько единиц доступно для выкладки со склада.",
    )

    class Meta:
        verbose_name = "Остаток на складе"
        verbose_name_plural = "Остатки на складе"

    def __str__(self) -> str:
        return f"{self.product.sku}: {self.quantity} шт."


class PlacementTask(models.Model):
    """Задача на выкладку: создаётся автоматически из планограммы и остатка на складе."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Создана"
        PENDING = "PENDING", "Ожидает"  # устаревший alias, мигрируется в CREATED
        IN_PROGRESS = "IN_PROGRESS", "Выполняется"
        COMPLETED = "COMPLETED", "Завершено"
        FAILED = "FAILED", "Проблема"
        CANCELLED = "CANCELLED", "Отменена"

    planogram = models.ForeignKey(
        Planogram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_tasks",
        verbose_name="Планограмма",
        help_text="Источник задачи; пусто для устаревших записей до введения планограмм.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="placement_tasks",
        verbose_name="Товар",
        help_text="Товар, который нужно выложить.",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="placement_tasks",
        verbose_name="Оборудование",
        help_text="Стеллаж, холодильник и т.п., куда нужно отнести товар.",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="Количество",
        help_text="Сколько единиц товара выложить.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="Статус",
    )
    batch = models.ForeignKey(
        "ProductBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_tasks",
        verbose_name="Партия (FEFO)",
        help_text="Партия FEFO, подобранная при создании задачи (списание при COMPLETED).",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_tasks",
        verbose_name="Исполнитель",
    )
    photo_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Фото отчёта (URL)",
    )
    slot_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="QR слота подтверждён",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершена",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    class Meta:
        verbose_name = "Задача на выкладку"
        verbose_name_plural = "Задачи на выкладку"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("planogram",),
                condition=models.Q(
                    status__in=("CREATED", "PENDING", "IN_PROGRESS"),
                ),
                name="uniq_placementtask_open_planogram",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} → {self.equipment.name} ({self.quantity} шт., {self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in (
            self.Status.CREATED,
            self.Status.PENDING,
            self.Status.IN_PROGRESS,
        )


class PlacementTaskScan(models.Model):
    """Зафиксированный скан единицы при выкладке."""

    task = models.ForeignKey(
        PlacementTask,
        on_delete=models.CASCADE,
        related_name="scans",
        verbose_name="Задача выкладки",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="placement_scans",
        verbose_name="Товар",
    )
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_scans",
        verbose_name="Партия",
    )
    serial_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Серийный номер",
    )
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_scans",
        verbose_name="Сканировал",
    )
    scanned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время скана",
    )

    class Meta:
        verbose_name = "Скан выкладки"
        verbose_name_plural = "Сканы выкладки"
        ordering = ("scanned_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("task", "serial_number"),
                condition=models.Q(serial_number__isnull=False),
                name="uniq_placement_scan_task_serial",
            ),
        ]

    def __str__(self) -> str:
        label = self.serial_number or "unit"
        return f"Scan {label} → task #{self.task_id}"


class ShelfClearingTask(models.Model):
    """Задача на уборку товара с полки обратно на склад."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Создана"
        PENDING = "PENDING", "Ожидает"
        IN_PROGRESS = "IN_PROGRESS", "Выполняется"
        COMPLETED = "COMPLETED", "Завершено"
        FAILED = "FAILED", "Проблема"
        CANCELLED = "CANCELLED", "Отменена"

    planogram = models.ForeignKey(
        Planogram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clearing_tasks",
        verbose_name="Планограмма",
    )
    slot = models.ForeignKey(
        EquipmentSlot,
        on_delete=models.CASCADE,
        related_name="clearing_tasks",
        verbose_name="Слот",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="clearing_tasks",
        verbose_name="Товар",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="clearing_tasks",
        verbose_name="Оборудование",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="Количество",
        help_text="Сколько единиц убрать с полки на склад.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="Статус",
    )
    batch = models.ForeignKey(
        "ProductBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clearing_tasks",
        verbose_name="Партия для возврата",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clearing_tasks",
        verbose_name="Исполнитель",
    )
    photo_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Фото отчёта (URL)",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершена",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    class Meta:
        verbose_name = "Задача уборки на склад"
        verbose_name_plural = "Задачи уборки на склад"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("slot",),
                condition=models.Q(status="CREATED"),
                name="uniq_clearingtask_created_slot",
            ),
        ]

    def __str__(self) -> str:
        return f"Убрать: {self.product} ← {self.equipment.name} ({self.quantity} шт., {self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in (
            self.Status.CREATED,
            self.Status.PENDING,
            self.Status.IN_PROGRESS,
        )


class PlacementChatMessage(models.Model):
    """Чат по задаче на выкладку (проблема на складе / FEFO)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    placement_task = models.ForeignKey(
        PlacementTask,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Задача на выкладку",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="placement_chat_messages",
        verbose_name="Отправитель",
    )
    text = models.TextField(blank=True, verbose_name="Текст")
    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Изображение (URL)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Отправлено")

    class Meta:
        verbose_name = "Сообщение чата (выкладка)"
        verbose_name_plural = "Сообщения чата (выкладка)"
        ordering = ("created_at",)


class ShelfWriteOff(models.Model):
    """Журнал списания товара с витрины (слота)."""

    class Reason(models.TextChoices):
        EXPIRED_PLACEMENT_BATCH = (
            "EXPIRED_PLACEMENT_BATCH",
            "Просрочена партия последней выкладки",
        )
        EXPIRED_BATCH = "EXPIRED_BATCH", "Просроченная партия"
        MANUAL = "MANUAL", "Ручное списание"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="shelf_write_offs",
        verbose_name="Магазин",
    )
    slot = models.ForeignKey(
        EquipmentSlot,
        on_delete=models.CASCADE,
        related_name="write_offs",
        verbose_name="Слот",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="shelf_write_offs",
        verbose_name="Товар",
    )
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shelf_write_offs",
        verbose_name="Партия",
    )
    planogram = models.ForeignKey(
        Planogram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_offs",
        verbose_name="Планограмма",
    )
    placement_task = models.ForeignKey(
        PlacementTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shelf_write_offs",
        verbose_name="Задача выкладки",
    )
    quantity = models.PositiveIntegerField(verbose_name="Списано, шт.")
    reason = models.CharField(
        max_length=40,
        choices=Reason.choices,
        default=Reason.EXPIRED_PLACEMENT_BATCH,
        verbose_name="Причина",
    )
    write_off_task = models.ForeignKey(
        "WriteOffTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shelf_write_offs",
        verbose_name="Задача списания",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Списание с полки"
        verbose_name_plural = "Списания с полок"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.product} −{self.quantity} шт. ({self.slot_id})"


class WriteOffTask(models.Model):
    """Задание сотруднику на списание товара со склада или с полки."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Создана"
        PENDING = "PENDING", "Ожидает"
        IN_PROGRESS = "IN_PROGRESS", "Выполняется"
        COMPLETED = "COMPLETED", "Завершено"
        CANCELLED = "CANCELLED", "Отменена"

    class Location(models.TextChoices):
        WAREHOUSE = "WAREHOUSE", "Склад"
        SHELF = "SHELF", "Полка"

    class Trigger(models.TextChoices):
        EXPIRED_AUTO = "EXPIRED_AUTO", "Просрочка (авто)"
        MANUAL = "MANUAL", "Ручное списание"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="write_off_tasks",
        verbose_name="Магазин",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="write_off_tasks",
        verbose_name="Товар",
    )
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Партия",
    )
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="Статус",
    )
    location = models.CharField(
        max_length=20,
        choices=Location.choices,
        verbose_name="Место списания",
    )
    trigger = models.CharField(
        max_length=20,
        choices=Trigger.choices,
        default=Trigger.EXPIRED_AUTO,
        verbose_name="Источник",
    )
    reason = models.TextField(blank=True, verbose_name="Причина / комментарий")
    slot = models.ForeignKey(
        EquipmentSlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Слот",
    )
    planogram = models.ForeignKey(
        Planogram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Планограмма",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Оборудование",
    )
    placement_task = models.ForeignKey(
        PlacementTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Задача выкладки",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_write_off_tasks",
        verbose_name="Создал",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="write_off_tasks",
        verbose_name="Исполнитель",
    )
    photo_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Фото отчёта (URL)",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Задача на списание"
        verbose_name_plural = "Задачи на списание"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("batch",),
                condition=models.Q(
                    status="CREATED",
                    location="WAREHOUSE",
                ),
                name="uniq_writeofftask_created_warehouse_batch",
            ),
            models.UniqueConstraint(
                fields=("batch", "slot"),
                condition=models.Q(
                    status="CREATED",
                    location="SHELF",
                ),
                name="uniq_writeofftask_created_shelf_batch_slot",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Списать: {self.product} — {self.quantity} шт. "
            f"({self.location}, {self.status})"
        )


class WarehouseWriteOff(models.Model):
    """Журнал списания товара со склада (партия)."""

    class Reason(models.TextChoices):
        EXPIRED_BATCH = "EXPIRED_BATCH", "Просроченная партия"
        MANUAL = "MANUAL", "Ручное списание"

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="warehouse_write_offs",
        verbose_name="Магазин",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="warehouse_write_offs",
        verbose_name="Товар",
    )
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_write_offs",
        verbose_name="Партия",
    )
    write_off_task = models.ForeignKey(
        WriteOffTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_write_offs",
        verbose_name="Задача списания",
    )
    quantity = models.PositiveIntegerField(verbose_name="Списано, шт.")
    reason = models.CharField(
        max_length=40,
        choices=Reason.choices,
        default=Reason.EXPIRED_BATCH,
        verbose_name="Причина",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Списание со склада"
        verbose_name_plural = "Списания со склада"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.product} −{self.quantity} шт. (склад)"


class StaffTask(models.Model):
    """Ручное поручение менеджера (уборка, проверки и т.п.), необязательно привязано к полке."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Создана"
        IN_PROGRESS = "IN_PROGRESS", "Выполняется"
        COMPLETED = "COMPLETED", "Завершена"
        CANCELLED = "CANCELLED", "Отменена"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Описание")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_staff_tasks",
        verbose_name="Создал",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_tasks",
        verbose_name="Исполнитель",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name="Статус",
    )
    zone = models.ForeignKey(
        "Zone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_tasks",
        verbose_name="Зона",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_tasks",
        verbose_name="Оборудование",
    )
    slot = models.ForeignKey(
        EquipmentSlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_tasks",
        verbose_name="Слот",
    )
    requires_photo = models.BooleanField(
        default=False,
        verbose_name="Требуется фотоотчёт",
    )
    photo_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Фото отчёта (URL)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")

    class Meta:
        verbose_name = "Поручение сотруднику"
        verbose_name_plural = "Поручения сотрудникам"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class ChatMessage(models.Model):
    """Сообщение чата, привязанное к ручному поручению StaffTask."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_task = models.ForeignKey(
        StaffTask,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Поручение",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        verbose_name="Отправитель",
    )
    text = models.TextField(verbose_name="Текст", blank=True)
    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Изображение (URL)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Отправлено")

    class Meta:
        verbose_name = "Сообщение чата"
        verbose_name_plural = "Сообщения чата"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.sender}: {self.text[:40]}"


class Shelf(models.Model):
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="shelves",
        verbose_name="Оборудование",
        help_text="Стеллаж/витрина/холодильник, к которому относится полка.",
    )
    level = models.PositiveIntegerField(
        verbose_name="Номер полки",
        help_text="Номер полки снизу вверх (1 — нижняя).",
    )
    width = models.FloatField(
        verbose_name="Ширина (см)",
        help_text="Внутренняя ширина полки в сантиметрах.",
    )
    height = models.FloatField(
        verbose_name="Высота (см)",
        help_text="Внутренняя высота полки в сантиметрах.",
    )
    depth = models.FloatField(
        verbose_name="Глубина (см)",
        help_text="Внутренняя глубина полки в сантиметрах.",
    )
    capacity_notes = models.TextField(
        blank=True,
        verbose_name="Примечания по вместимости",
        help_text="Дополнительная информация о грузоподъёмности, шаге крючков и т.п.",
    )

    class Meta:
        verbose_name = "Полка"
        verbose_name_plural = "Полки"
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "level"],
                name="uniq_shelf_equipment_level",
            )
        ]

    def __str__(self) -> str:
        return f"{self.equipment} — полка {self.level}"

    def calculate_max_capacity(self, product: Product) -> int:
        """
        Оценка максимального числа целых единиц товара на полке (решётка по осям X/Y/Z).

        Полка (Shelf) задаёт внутренние размеры в сантиметрах; товар (Product) — в
        миллиметрах. Перед расчётом размеры полки переводятся в мм (×10), чтобы
        сравнение с габаритами товара было в одной системе единиц.

        Далее по каждой оси считается, сколько целых «кирпичей» помещается вдоль
        ширины, глубины и высоты (целочисленное деление // — без дробных долей
        единицы товара). Итоговая вместимость — произведение трёх множителей
        (упрощённая модель укладки параллелепипедов без зазоров и без поворота SKU).

        При неполных или нулевых габаритах товара возвращается 0.
        """
        if product is None:
            return 0

        pw, ph, pd = product.width, product.height, product.depth
        if pw is None or ph is None or pd is None:
            return 0
        if pw <= 0 or ph <= 0 or pd <= 0:
            return 0

        sw, sh, sd = self.width, self.height, self.depth
        if sw is None or sh is None or sd is None:
            return 0
        if sw <= 0 or sh <= 0 or sd <= 0:
            return 0

        # Полка: см → мм (Float); товар уже в мм.
        sw_mm = sw * 10.0
        sh_mm = sh * 10.0
        sd_mm = sd * 10.0

        nx = int(sw_mm // pw)
        ny = int(sd_mm // pd)
        if getattr(product, "is_stackable", True):
            nz = int(sh_mm // ph)
        else:
            nz = 1

        return nx * ny * nz


class PlanogramEquipment(models.Model):
    """Оборудование планограммы (логика выкладки), не путать с Equipment плана зала."""

    class DisplayLogic(models.TextChoices):
        SURFACE = "surface", "Полка"
        LINEAR = "linear", "Вешалка"
        BULK = "bulk", "Емкость"
        GRID = "grid", "Сетка/Крючки"
        SPOT = "spot", "Экспозиция"

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
        help_text="Название торгового оборудования.",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="planogram_equipment",
        verbose_name="Магазин",
        help_text="Магазин, в котором установлено оборудование.",
    )
    pos_x = models.FloatField(
        verbose_name="Позиция X",
        help_text="Координата X на плане магазина (единица измерения по договорённости).",
    )
    pos_y = models.FloatField(
        verbose_name="Позиция Y",
        help_text="Координата Y на плане магазина (единица измерения по договорённости).",
    )
    rotation = models.FloatField(
        default=0.0,
        verbose_name="Поворот",
        help_text="Поворот оборудования на плане (в градусах).",
    )
    width = models.FloatField(
        verbose_name="Ширина (мм)",
        help_text="Ширина оборудования в миллиметрах.",
    )
    height = models.FloatField(
        verbose_name="Высота (мм)",
        help_text="Высота оборудования в миллиметрах.",
    )
    depth = models.FloatField(
        verbose_name="Глубина (мм)",
        help_text="Глубина оборудования в миллиметрах.",
    )
    display_logic = models.CharField(
        max_length=20,
        choices=DisplayLogic.choices,
        default=DisplayLogic.SURFACE,
        verbose_name="Логика выкладки",
        help_text="Логика расчёта размещения товаров на оборудовании.",
    )

    class Meta:
        verbose_name = "Legacy: оборудование планограммы"
        verbose_name_plural = "Legacy: оборудование планограммы (не использовать)"

    def __str__(self) -> str:
        return f"{self.name} — {self.store}"


class ShelfLevel(models.Model):
    equipment = models.ForeignKey(
        PlanogramEquipment,
        on_delete=models.CASCADE,
        related_name="shelf_levels",
        verbose_name="Оборудование",
        help_text="Оборудование, к которому относится уровень/полка.",
    )
    level_number = models.PositiveIntegerField(
        verbose_name="Номер уровня",
        help_text="Порядковый номер уровня/полки.",
    )
    width = models.FloatField(
        verbose_name="Ширина (мм)",
        help_text="Ширина уровня в миллиметрах.",
    )
    height = models.FloatField(
        verbose_name="Высота (мм)",
        help_text="Высота уровня в миллиметрах.",
    )
    depth = models.FloatField(
        verbose_name="Глубина (мм)",
        help_text="Глубина уровня в миллиметрах.",
    )
    hooks_count = models.IntegerField(
        default=0,
        verbose_name="Количество крючков",
        help_text="Количество крючков для сетки/крючков (grid).",
    )

    class Meta:
        verbose_name = "Legacy: уровень планограммы"
        verbose_name_plural = "Legacy: уровни планограммы (не использовать)"
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "level_number"],
                name="uniq_shelflevel_equipment_level_number",
            )
        ]

    def __str__(self) -> str:
        return f"{self.equipment} — уровень {self.level_number}"


class Placement(models.Model):
    shelf_level = models.ForeignKey(
        ShelfLevel,
        on_delete=models.CASCADE,
        related_name="placements",
        verbose_name="Уровень/полка",
        help_text="Уровень оборудования, на котором размещён товар.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="placements",
        verbose_name="Товар",
        help_text="Товар, размещённый на уровне/полке.",
    )

    class Meta:
        verbose_name = "Legacy: размещение"
        verbose_name_plural = "Legacy: размещения (не использовать)"
        constraints = [
            models.UniqueConstraint(
                fields=["shelf_level", "product"],
                name="uniq_placement_shelflevel_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product} на {self.shelf_level}"

    def calculate_capacity(self) -> int:
        equipment = self.shelf_level.equipment
        shelf = self.shelf_level
        product = self.product

        def safe_floor(value: float) -> int:
            if value is None or value <= 0:
                return 0
            return int(math.floor(value))

        logic = equipment.display_logic

        if logic == PlanogramEquipment.DisplayLogic.SURFACE:
            if not product.width or not product.depth:
                return 0
            capacity = (shelf.width / product.width) * (shelf.depth / product.depth)
            return safe_floor(capacity)

        if logic == PlanogramEquipment.DisplayLogic.LINEAR:
            if not product.depth:
                return 0
            capacity = shelf.width / product.depth
            return safe_floor(capacity)

        if logic == PlanogramEquipment.DisplayLogic.BULK:
            if not product.width or not product.height or not product.depth:
                return 0
            shelf_volume = shelf.width * shelf.height * shelf.depth
            product_volume = product.width * product.height * product.depth
            if product_volume <= 0:
                return 0
            capacity = shelf_volume / product_volume
            return safe_floor(capacity)

        if logic == PlanogramEquipment.DisplayLogic.GRID:
            return max(0, int(shelf.hooks_count))

        if logic == PlanogramEquipment.DisplayLogic.SPOT:
            return 1

        return 0


class LegacyPlanogramTask(models.Model):
    """Устаревшая задача планограммы (Placement); не используется в API зала."""

    class Status(models.TextChoices):
        TODO = "todo", "К выполнению"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Готово"

    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок",
        help_text="Короткое название задачи.",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Подробное описание задачи.",
    )
    assigned_to = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_planogram_tasks",
        verbose_name="Исполнитель",
        help_text="Пользователь, которому назначена задача.",
    )
    placement = models.ForeignKey(
        Placement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_tasks",
        verbose_name="Размещение",
        help_text="Размещение (планограмма), к которому относится задача.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
        verbose_name="Статус",
        help_text="Текущий статус задачи.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата и время создания задачи.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата завершения",
        help_text="Дата и время завершения задачи.",
    )
    report_photo = models.ImageField(
        upload_to="task_reports/",
        null=True,
        blank=True,
        verbose_name="Фото отчёта",
        help_text="Фотография отчёта о выполнении задачи.",
    )

    class Meta:
        verbose_name = "Задача (legacy планограмма)"
        verbose_name_plural = "Задачи (legacy планограмма)"

    def __str__(self) -> str:
        return self.title
