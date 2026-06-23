from django.contrib import admin
from django.utils.html import format_html
from .models import SocioComercial, PedidoFomy


@admin.register(SocioComercial)
class SocioComercialAdmin(admin.ModelAdmin):
    list_display  = ('nombre','tipo_negocio','ciudad','estado',
                     'activo','mostrar_en_mapa','destacado','preview_contacto')
    list_filter   = ('activo','mostrar_en_mapa','destacado','estado')
    list_editable = ('activo','mostrar_en_mapa','destacado')
    search_fields = ('nombre','ciudad','estado','contacto')
    fieldsets = (
        ('Información General', {
            'fields': ('nombre','tipo_negocio','slogan','descripcion','horario','usuario')
        }),
        ('Imágenes', {
            'fields': ('logo','foto_negocio')
        }),
        ('Contacto', {
            'fields': ('contacto','telefono','email',
                       'whatsapp_1','whatsapp_2','facebook_url','instagram_url')
        }),
        ('Ubicación', {
            'fields': ('direccion','ciudad','estado','latitud','longitud')
        }),
        ('Configuración', {
            'fields': ('activo','mostrar_en_mapa','destacado','notas')
        }),
    )

    def preview_contacto(self, obj):
        icons = []
        if obj.whatsapp_1:
            icons.append(f'<a href="{obj.whatsapp_1_url}" target="_blank" style="color:#25D366">WA1</a>')
        if obj.whatsapp_2:
            icons.append(f'<a href="{obj.whatsapp_2_url}" target="_blank" style="color:#128C7E">WA2</a>')
        if obj.facebook_url:
            icons.append(f'<a href="{obj.facebook_url}" target="_blank" style="color:#1877F2">FB</a>')
        if obj.instagram_url:
            icons.append(f'<a href="{obj.instagram_url}" target="_blank" style="color:#E4405F">IG</a>')
        return format_html(' · '.join(icons)) if icons else '—'
    preview_contacto.short_description = 'Contacto'
    preview_contacto.allow_tags = True


@admin.register(PedidoFomy)
class PedidoFomyAdmin(admin.ModelAdmin):
    list_display  = ('socio','figura','cantidad','total','estado','pagado_en','creado')
    list_filter   = ('estado','creado')
    list_editable = ('estado',)
    search_fields = ('socio__nombre','figura__nombre')
    readonly_fields = ('stripe_session_id','stripe_payment_intent','pagado_en','creado','actualizado')
