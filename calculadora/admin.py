from django.contrib import admin
from .models import PlanCalculadora, HistorialCalculo


@admin.register(PlanCalculadora)
class PlanCalculadoraAdmin(admin.ModelAdmin):
    list_display = ('plan', 'max_mb', 'max_paginas', 'descripcion')
    list_editable = ('max_mb', 'max_paginas')


@admin.register(HistorialCalculo)
class HistorialCalculoAdmin(admin.ModelAdmin):
    list_display = ('nombre_archivo', 'usuario', 'num_paginas', 'tipo_hoja',
                    'costo_total', 'tiempo_proceso', 'ip_cliente', 'creado')
    list_filter = ('tipo_hoja', 'creado')
    search_fields = ('nombre_archivo', 'usuario__username', 'ip_cliente')
    readonly_fields = ('creado',)
    date_hierarchy = 'creado'
