from django.contrib import admin
from .models import Cotizacion, DetalleCotizacion, TarifaEnvio


@admin.register(TarifaEnvio)
class TarifaEnvioAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'precio_base', 'peso_base_kg', 'precio_kg_extra', 'activa')

    def has_add_permission(self, request):
        return not TarifaEnvio.objects.exists()  # solo un registro


class DetalleCotizacionInline(admin.TabularInline):
    model = DetalleCotizacion
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal')


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'estado', 'metodo_envio', 'costo_envio', 'total_estimado', 'peso_total', 'fecha_requerida', 'creado')
    list_filter = ('estado', 'metodo_envio', 'creado')
    search_fields = ('cliente__username', 'cliente__first_name', 'cliente__last_name')
    readonly_fields = ('peso_total', 'total_estimado', 'costo_envio', 'creado', 'actualizado')
    fieldsets = (
        ('General', {'fields': ('cliente', 'estado', 'notas', 'peso_total', 'total_estimado', 'creado', 'actualizado')}),
        ('Envío', {'fields': ('metodo_envio', 'costo_envio', 'direccion_calle', 'direccion_colonia', 'direccion_ciudad', 'direccion_estado', 'direccion_cp', 'fecha_requerida', 'notas_entrega')}),
    )
    inlines = [DetalleCotizacionInline]
