from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import StudentProfile, User


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "full_name", "role", "is_active", "must_change_password", "last_login"]
    list_filter = ["role", "is_active"]
    search_fields = ["username", "full_name"]
    ordering = ["username"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("full_name", "role", "must_change_password", "token_version")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "full_name", "role", "password1", "password2")}),)
    inlines = [StudentProfileInline]
