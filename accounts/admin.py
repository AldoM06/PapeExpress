from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'rol',
                    'empresa', 'is_active', 'verificado_display', 'precio_envio_especial', 'foto_negocio_preview')
    list_filter = ('rol', 'is_active', 'is_staff', 'verificado')
    actions = ['aprobar_verificacion', 'rechazar_verificacion']
    fieldsets = UserAdmin.fieldsets + (
        ('Información PapeExpress', {
            'fields': ('rol', 'empresa', 'telefono', 'foto', 'foto_negocio', 'verificado', 'precio_envio_especial')
        }),
        ('Dirección de envío por defecto', {
            'fields': ('dir_calle', 'dir_colonia', 'dir_ciudad', 'dir_estado', 'dir_cp'),
            'classes': ('collapse',),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información PapeExpress', {'fields': ('rol', 'empresa', 'telefono')}),
    )
    search_fields = ('username', 'email', 'first_name', 'last_name', 'empresa')
    readonly_fields = ('foto_negocio_preview',)

    @admin.display(description='Verificado', boolean=True)
    def verificado_display(self, obj):
        return obj.verificado

    @admin.display(description='Foto negocio')
    def foto_negocio_preview(self, obj):
        if obj.foto_negocio:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="height:60px;border-radius:6px;object-fit:cover">'
                '</a>',
                obj.foto_negocio.url, obj.foto_negocio.url
            )
        return '—'

    @admin.action(description='✅ Aprobar verificación de negocio')
    def aprobar_verificacion(self, request, queryset):
        actualizados = queryset.filter(rol='cliente').update(verificado=True)
        self.message_user(request, f'{actualizados} cliente(s) aprobado(s) correctamente.', messages.SUCCESS)

    @admin.action(description='❌ Rechazar verificación de negocio')
    def rechazar_verificacion(self, request, queryset):
        for usuario in queryset.filter(rol='cliente'):
            if usuario.foto_negocio:
                usuario.foto_negocio.delete(save=False)
                usuario.foto_negocio = None
            usuario.verificado = False
            usuario.save(update_fields=['foto_negocio', 'verificado'])
        self.message_user(request, f'Verificación rechazada para los clientes seleccionados.', messages.WARNING)
