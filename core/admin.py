from django.contrib import admin
from .models import Producto, Categoria, MensajeContacto, ConfiguracionSitio


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'descripcion')
    list_filter = ('tipo',)
    search_fields = ('nombre',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio', 'disponible', 'mostrar_en_portada', 'destacado', 'orden')
    list_filter = ('categoria', 'disponible', 'mostrar_en_portada', 'destacado', 'categoria__tipo')
    list_editable = ('disponible', 'mostrar_en_portada', 'destacado', 'orden')
    search_fields = ('nombre', 'descripcion')
    ordering = ('orden', 'nombre')


@admin.register(MensajeContacto)
class MensajeContactoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'asunto', 'leido', 'creado')
    list_filter = ('leido',)
    list_editable = ('leido',)
    readonly_fields = ('nombre', 'email', 'telefono', 'asunto', 'mensaje', 'creado')
    search_fields = ('nombre', 'email', 'asunto')


@admin.register(ConfiguracionSitio)
class ConfiguracionSitioAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ConfiguracionSitio.objects.exists()
