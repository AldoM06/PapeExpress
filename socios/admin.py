from django.contrib import admin
from .models import SocioComercial, PedidoFomy


@admin.register(SocioComercial)
class SocioComercialAdmin(admin.ModelAdmin):
    list_display  = ('nombre','tipo_negocio','ciudad','estado','activo','mostrar_en_mapa','usuario')
    list_filter   = ('activo','mostrar_en_mapa','estado')
    list_editable = ('activo','mostrar_en_mapa')
    search_fields = ('nombre','ciudad','estado','contacto')
    fieldsets = (
        ('Información General', {'fields':('nombre','tipo_negocio','contacto','telefono','email','usuario')}),
        ('Ubicación', {'fields':('direccion','ciudad','estado','latitud','longitud')}),
        ('Configuración', {'fields':('activo','mostrar_en_mapa','notas')}),
    )


@admin.register(PedidoFomy)
class PedidoFomyAdmin(admin.ModelAdmin):
    list_display  = ('socio','figura','cantidad','total','estado','pagado_en','creado')
    list_filter   = ('estado','creado')
    list_editable = ('estado',)
    search_fields = ('socio__nombre','figura__nombre')
    readonly_fields = ('stripe_session_id','stripe_payment_intent','pagado_en','creado','actualizado')
