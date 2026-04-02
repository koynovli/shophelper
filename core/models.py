import math
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
        help_text="Где физически учитывается товар: заказ, склад или витрина.",
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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_supply_orders",
        verbose_name="Кем создан",
        help_text="Пользователь, оформивший заказ.",
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
        verbose_name="Количество",
        help_text="Заказанное количество единиц по строке.",
    )
    price_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Цена за единицу",
        help_text="Договорная закупочная цена за единицу в этой строке.",
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity} (заказ {self.order_id})"


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
        max_digits=12,
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
        return f"{self.product.sku} @ {self.store} → до {self.expiration_date}"

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
