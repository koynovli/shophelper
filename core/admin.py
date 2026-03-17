from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Category,
    Equipment,
    Placement,
    Product,
    ShelfLevel,
    Store,
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
