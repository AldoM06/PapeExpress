from django.contrib import admin
from .models import FiguraFomy, FotoFigura, HistorialEtapa, Libreta


class FotoInline(admin.TabularInline):
    model  = FotoFigura
    extra  = 0
    max_num = 4
    fields = ('foto','descripcion','orden')


class HistorialInline(admin.TabularInline):
    model        = HistorialEtapa
    extra        = 0
    readonly_fields = ('etapa_anterior','etapa_nueva','usuario','notas','fecha')
    can_delete   = False


@admin.register(FiguraFomy)
class FiguraFomyAdmin(admin.ModelAdmin):
    list_display  = ('nombre','etapa_actual','cantidad_planificada','cantidad_disponible',
                     'precio_venta','tiene_fomy','actualizado')
    list_filter   = ('etapa_actual','tiene_fomy')
    list_editable = ('etapa_actual','tiene_fomy','cantidad_disponible')
    search_fields = ('nombre',)
    inlines       = [FotoInline, HistorialInline]
    fieldsets = (
        ('General', {'fields':('nombre','descripcion','imagen_referencia','etapa_actual','responsable')}),
        ('Producción', {'fields':('cantidad_planificada','cantidad_disponible','costo_estimado','precio_venta','tiene_fomy','notas')}),
        ('Archivos', {'fields':('archivo_studio3','archivo_instrucciones_pdf','archivo_instrucciones_word')}),
    )


@admin.register(Libreta)
class LibretaAdmin(admin.ModelAdmin):
    list_display  = ('nombre','num_hojas','tipo_pasta','precio','disponible','mostrar_en_portada')
    list_editable = ('disponible','mostrar_en_portada')


@admin.register(HistorialEtapa)
class HistorialEtapaAdmin(admin.ModelAdmin):
    list_display  = ('figura','etapa_anterior','etapa_nueva','usuario','fecha')
    readonly_fields = ('figura','etapa_anterior','etapa_nueva','usuario','fecha')
