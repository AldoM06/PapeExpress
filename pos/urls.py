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

    # Productos
    path('productos/lista/',        views.productos_lista,    name='pos_productos_lista'),
    path('productos/nuevo/',        views.crear_producto,     name='pos_crear_producto'),
    path('productos/<int:pk>/editar/', views.editar_producto, name='pos_editar_producto'),

    # Inventario
    path('inventario/',             views.inventario_view,    name='pos_inventario'),
    path('inventario/entrada/',     views.entrada_mercancia,  name='entrada_mercancia'),

    # Compras y tickets
    path('compras/',                views.compras_view,       name='pos_compras'),
    path('compras/analizar-ticket/',views.analizar_ticket,    name='analizar_ticket'),

    # Comparar precios
    path('precios/comparar/',       views.comparar_precios,   name='comparar_precios'),

    # Ingresos del día
    path('ingresos/',               views.ingresos_dia,          name='pos_ingresos'),

    # Dashboard admin
    path('admin-pos/',              views.dashboard_admin_pos,   name='dashboard_admin_pos'),
    path('admin-pos/barrido/',      views.barrido_manual,        name='barrido_manual'),

    # Dashboard de sucursal (gerente/vendedor/almacén/cajero)
    path('mi-sucursal/',            views.dashboard_sucursal,    name='dashboard_sucursal'),

    # Gestión de sucursales
    path('sucursales/',             views.dashboard_sucursales,  name='dashboard_sucursales'),
    path('sucursales/<int:suc_pk>/asignar/', views.asignar_usuario_sucursal, name='asignar_usuario_sucursal'),
    path('sucursales/asignacion/<int:pk>/quitar/', views.quitar_usuario_sucursal, name='quitar_usuario_sucursal'),
]
