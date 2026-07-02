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
    path('productos/margenes/',     views.margenes_productos, name='pos_margenes'),
    path('productos/comparar/',     views.comparar_precios_sucursales, name='pos_comparar_precios'),
    path('productos/<int:prod_id>/igualar/', views.igualar_precio_sucursales, name='pos_igualar_precio'),
    path('precios/<int:pp_id>/actualizar/', views.actualizar_precio, name='actualizar_precio'),

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

    # Ventas canceladas
    path('canceladas/',             views.ventas_canceladas,     name='ventas_canceladas'),

    # Cancelación de ventas
    path('ventas/<int:venta_pk>/cancelar/',                       views.cancelar_venta,                   name='cancelar_venta'),
    path('ventas/<int:venta_pk>/solicitar-cancelacion-telegram/', views.solicitar_cancelacion_telegram,   name='solicitar_cancelacion_telegram'),
    path('autorizar-cancelacion/<str:token>/',                    views.autorizar_cancelacion_view,        name='autorizar_cancelacion'),

    # Top productos
    path('api/top-productos/',      views.top_productos_api,     name='pos_top_productos'),

    # Recargas y pagos de servicio
    path('servicios/',                  views.servicios_view,        name='servicios_pos'),
    path('servicios/<int:pk>/eliminar/', views.servicio_eliminar,    name='servicio_eliminar'),

    # Caja diaria
    path('caja/apertura/',              views.apertura_caja,         name='apertura_caja'),
    path('caja/retiro/',                views.retiro_efectivo,       name='retiro_efectivo'),
    path('caja/cierre/',                views.cierre_caja,           name='cierre_caja'),
    path('caja/resumen/<int:pk>/',      views.resumen_cierre_caja,   name='resumen_cierre_caja'),
    path('caja/revisar/<int:pk>/',      views.revisar_cierre_caja,   name='revisar_cierre_caja'),
    path('caja/historial/',             views.historial_cierres,     name='historial_cierres'),

    # Traspasos entre sucursales
    path('traspasos/',                          views.traspasos_lista,         name='traspasos_lista'),
    path('traspasos/nuevo/',                    views.traspaso_nuevo,          name='traspaso_nuevo'),
    path('traspasos/<int:pk>/aprobar/',         views.traspaso_aprobar,        name='traspaso_aprobar'),
    path('traspasos/<int:pk>/recibir/',         views.traspaso_recibir,        name='traspaso_recibir'),
    path('traspasos/<int:pk>/cancelar/',        views.traspaso_cancelar,       name='traspaso_cancelar'),
    path('api/traspaso-productos/',             views.traspaso_productos_api,  name='traspaso_productos_api'),

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
