from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'rol', 'empresa', 'is_active')
    list_filter = ('rol', 'is_active', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Información PapeExpress', {'fields': ('rol', 'empresa', 'telefono', 'foto')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información PapeExpress', {'fields': ('rol', 'empresa', 'telefono')}),
    )
    search_fields = ('username', 'email', 'first_name', 'last_name', 'empresa')
