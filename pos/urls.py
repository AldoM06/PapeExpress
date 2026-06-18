from django.urls import path
from . import views

urlpatterns = [
    # POS principal
    path('',                        views.pos_view,           name='pos'),
    path('api/productos/',          views.productos_api,      name='pos_productos_api'),
    path('api/venta/',              views.procesar_venta,     name='pos_procesar_venta'),

    # Créditos y abonos
    path('creditos/',               views.ventas_credito,     name='ventas_credito'),
    path('creditos/<int:venta_pk>/abono/', views.agregar_abono, name='agregar_abono'),

    # Anticipos
    path('anticipos/',              views.anticipos_view,     name='anticipos'),

    # Inventario
    path('inventario/',             views.inventario_view,    name='pos_inventario'),

    # Compras y tickets
    path('compras/',                views.compras_view,       name='pos_compras'),
    path('compras/analizar-ticket/',views.analizar_ticket,    name='analizar_ticket'),

    # Comparar precios
    path('precios/comparar/',       views.comparar_precios,   name='comparar_precios'),

    # Dashboard admin
    path('admin-pos/',              views.dashboard_admin_pos, name='dashboard_admin_pos'),
    path('admin-pos/barrido/',      views.barrido_manual,     name='barrido_manual'),
]
