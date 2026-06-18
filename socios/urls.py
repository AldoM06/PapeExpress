from django.urls import path
from . import views

urlpatterns = [
    path('mapa/',                          views.mapa_socios,      name='mapa_socios'),
    path('api/',                           views.socios_api,        name='socios_api'),
    path('portal/',                        views.portal_socio,      name='portal_socio'),
    path('pedido/crear/',                  views.crear_pedido,      name='crear_pedido'),
    path('pedido/<int:pk>/exito/',         views.pedido_exitoso,    name='pedido_exitoso'),
    path('pedido/<int:pk>/cancelado/',     views.pedido_cancelado,  name='pedido_cancelado'),
    path('webhook/stripe/',               views.stripe_webhook,    name='stripe_webhook'),
]
