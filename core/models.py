import math

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


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор сети"
        MANAGER = "manager", "Менеджер магазина"
        STAFF = "staff", "Мерчандайзер"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STAFF,
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
        return self.role in {self.Role.MANAGER, self.Role.ADMIN}

    @property
    def is_merchandiser(self) -> bool:
        return self.role == self.Role.STAFF

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

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class Company(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"

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
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventories",
        verbose_name="Товар",
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество",
    )
    status = models.CharField(
        max_length=20,
        choices=LocationStatus.choices,
        default=LocationStatus.WAREHOUSE,
        verbose_name="Статус нахождения",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )

    class Meta:
        verbose_name = "Остаток"
        verbose_name_plural = "Остатки"
        constraints = [
            models.UniqueConstraint(
                fields=["store", "product"],
                name="uniq_inventory_store_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.store} — {self.product} ({self.quantity})"


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
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="supply_orders",
        verbose_name="Магазин",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Принят",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supply_orders",
        verbose_name="Кем создан",
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
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="supply_order_items",
        verbose_name="Товар",
    )
    expected_quantity = models.PositiveIntegerField(
        verbose_name="Ожидаемое количество",
    )
    actual_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Фактическое количество",
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"

    def __str__(self) -> str:
        return f"{self.product} × {self.expected_quantity} (заказ {self.order_id})"


class Equipment(models.Model):
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
        related_name="equipment",
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
        verbose_name = "Оборудование"
        verbose_name_plural = "Оборудование"

    def __str__(self) -> str:
        return f"{self.name} — {self.store}"


class ShelfLevel(models.Model):
    equipment = models.ForeignKey(
        Equipment,
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
        verbose_name = "Уровень/полка"
        verbose_name_plural = "Уровни/полки"
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
        verbose_name = "Размещение (планограмма)"
        verbose_name_plural = "Размещения (планограмма)"
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

        if logic == Equipment.DisplayLogic.SURFACE:
            if not product.width or not product.depth:
                return 0
            capacity = (shelf.width / product.width) * (shelf.depth / product.depth)
            return safe_floor(capacity)

        if logic == Equipment.DisplayLogic.LINEAR:
            if not product.depth:
                return 0
            capacity = shelf.width / product.depth
            return safe_floor(capacity)

        if logic == Equipment.DisplayLogic.BULK:
            if not product.width or not product.height or not product.depth:
                return 0
            shelf_volume = shelf.width * shelf.height * shelf.depth
            product_volume = product.width * product.height * product.depth
            if product_volume <= 0:
                return 0
            capacity = shelf_volume / product_volume
            return safe_floor(capacity)

        if logic == Equipment.DisplayLogic.GRID:
            return max(0, int(shelf.hooks_count))

        if logic == Equipment.DisplayLogic.SPOT:
            return 1

        return 0


class Task(models.Model):
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
        related_name="tasks",
        verbose_name="Исполнитель",
        help_text="Пользователь, которому назначена задача.",
    )
    placement = models.ForeignKey(
        Placement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
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
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"

    def __str__(self) -> str:
        return self.title
