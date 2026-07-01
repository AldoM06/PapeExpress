from django.contrib import admin
from django.utils.html import format_html
from .models import Producto, Categoria, MensajeContacto, ConfiguracionSitio, FotoProducto


class FotoProductoInline(admin.TabularInline):
    model  = FotoProducto
    extra  = 3
    fields = ('imagen', 'orden', 'preview')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.imagen:
            return format_html('<img src="{}" style="height:60px;border-radius:6px">', obj.imagen.url)
        return '—'
    preview.short_description = 'Vista previa'


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'descripcion')
    list_filter  = ('tipo',)
    search_fields = ('nombre',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'categoria', 'marca', 'precio', 'precio_mayoreo',
                     'peso', 'disponible', 'mostrar_en_portada', 'destacado', 'orden')
    list_filter   = ('categoria', 'disponible', 'mostrar_en_portada', 'destacado', 'categoria__tipo')
    list_editable = ('precio', 'precio_mayoreo', 'peso', 'disponible', 'mostrar_en_portada', 'destacado', 'orden')
    search_fields = ('nombre', 'descripcion', 'marca', 'sku')
    ordering      = ('orden', 'nombre')
    fieldsets = (
        ('General', {'fields': ('categoria', 'nombre', 'descripcion', 'imagen', 'disponible', 'mostrar_en_portada', 'destacado', 'orden')}),
        ('Precios', {'fields': ('precio', 'precio_mayoreo', 'peso')}),
        ('Detalles', {'fields': ('marca', 'sku', 'piezas_por_caja', 'contenido')}),
    )
    inlines = [FotoProductoInline]


@admin.register(MensajeContacto)
class MensajeContactoAdmin(admin.ModelAdmin):
    list_display    = ('nombre', 'email', 'asunto', 'leido', 'creado')
    list_filter     = ('leido',)
    list_editable   = ('leido',)
    readonly_fields = ('nombre', 'email', 'telefono', 'asunto', 'mensaje', 'creado')
    search_fields   = ('nombre', 'email', 'asunto')


@admin.register(ConfiguracionSitio)
class ConfiguracionSitioAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ConfiguracionSitio.objects.exists()
