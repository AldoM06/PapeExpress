from django.urls import path
from . import views

urlpatterns = [
    path('carrito/', views.carrito_view, name='carrito'),
    path('agregar/<int:producto_id>/', views.agregar_producto, name='agregar_producto'),
    path('quitar/<int:producto_id>/', views.quitar_producto, name='quitar_producto'),
    path('actualizar/<int:producto_id>/', views.actualizar_cantidad, name='actualizar_cantidad'),
    path('enviar/', views.enviar_cotizacion, name='enviar_cotizacion'),
    path('verificar/', views.subir_verificacion, name='subir_verificacion'),
    path('verificar/estado/', views.estado_verificacion, name='estado_verificacion'),
    path('historial/', views.historial_view, name='historial_cotizaciones'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
]
