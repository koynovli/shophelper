from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html

from .models import (
    Category,
    Company,
    Equipment,
    Inventory,
    Placement,
    Product,
    ProductBatch,
    ShelfLevel,
    Store,
    SupplyOrder,
    SupplyOrderItem,
    Task,
    User,
)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "created_at")
    search_fields = ("name", "address")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "store", "is_staff", "is_active")
    list_filter = ("role", "store", "is_staff", "is_active", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name", "phone")

    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Дополнительно",
            {
                "fields": (
                    "role",
                    "phone",
                    "store",
                )
            },
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Дополнительно",
            {
                "fields": (
                    "role",
                    "phone",
                    "store",
                )
            },
        ),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price")
    search_fields = ("sku", "name")
    list_filter = ("category",)


class SupplyOrderItemInline(admin.TabularInline):
    model = SupplyOrderItem
    extra = 0
    fields = ("product", "quantity", "price_per_unit")
    autocomplete_fields = ("product",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "store",
        "status",
        "total_amount",
        "created_at",
        "received_at",
        "created_by",
    )
    list_filter = ("status", "company", "store")
    search_fields = ("store__name", "company__name")
    autocomplete_fields = ("company", "store", "created_by")
    inlines = (SupplyOrderItemInline,)


@admin.register(SupplyOrderItem)
class SupplyOrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "price_per_unit")
    list_filter = ("order__status", "order__company", "order__store")
    search_fields = ("product__sku", "product__name", "order__id")
    autocomplete_fields = ("order", "product")


@admin.register(ProductBatch)
class ProductBatchAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "store",
        "current_quantity",
        "expiration_date_colored",
        "expiry_status_colored",
        "is_active",
    )
    list_filter = ("is_active", "store", "product")
    search_fields = ("product__sku", "product__name", "store__name")
    autocomplete_fields = ("product", "store", "supply_item")
    date_hierarchy = "expiration_date"

    @admin.display(description="Срок годности")
    def expiration_date_colored(self, obj: ProductBatch):
        days = obj.get_remaining_days()
        if obj.is_expired:
            color = "#b00020"
        elif days <= 7:
            color = "#c65f00"
        else:
            color = "#1b7f3a"
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            color,
            obj.expiration_date,
        )

    @admin.display(description="Статус срока")
    def expiry_status_colored(self, obj: ProductBatch):
        days = obj.get_remaining_days()
        if obj.is_expired:
            return format_html(
                '<span style="background:#fde8e8;color:#b00020;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">Просрочен</span>'
            )
        if days == 0:
            return format_html(
                '<span style="background:#fff4e0;color:#a05a00;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">Истекает сегодня</span>'
            )
        if days <= 7:
            return format_html(
                '<span style="background:#fff8e6;color:#8a5a00;padding:2px 8px;'
                'border-radius:4px;font-weight:600;">Осталось {} дн.</span>',
                days,
            )
        return format_html(
            '<span style="background:#e8f5e9;color:#1b5e20;padding:2px 8px;'
            'border-radius:4px;font-weight:600;">ОК ({} дн.)</span>',
            days,
        )


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("store", "product", "batch", "quantity", "status", "updated_at")
    list_filter = ("status", "store")
    search_fields = ("product__sku", "product__name", "store__name")
    autocomplete_fields = ("store", "product", "batch")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "store", "display_logic", "pos_x", "pos_y", "rotation")
    list_filter = ("store", "display_logic")
    search_fields = ("name",)


@admin.register(ShelfLevel)
class ShelfLevelAdmin(admin.ModelAdmin):
    list_display = ("equipment", "level_number", "width", "height", "depth", "hooks_count")
    list_filter = ("equipment__store", "equipment", "level_number")
    search_fields = ("equipment__name",)


@admin.register(Placement)
class PlacementAdmin(admin.ModelAdmin):
    list_display = ("product", "shelf_level", "capacity_preview")
    list_filter = ("shelf_level__equipment__store", "shelf_level__equipment__display_logic")
    search_fields = ("product__sku", "product__name")

    @admin.display(description="Вместимость")
    def capacity_preview(self, obj: Placement) -> int:
        return obj.calculate_capacity()


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "assigned_to", "created_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("title", "assigned_to__username", "assigned_to__email")
