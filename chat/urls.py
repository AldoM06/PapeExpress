from django.urls import path
from . import views

urlpatterns = [
    path('', views.iniciar_chat, name='chat_cliente'),
    path('iniciar/', views.iniciar_anonimo, name='chat_iniciar_anonimo'),
    path('enviar/', views.enviar_mensaje_cliente, name='chat_enviar'),
    path('<int:conv_id>/mensajes/', views.mensajes_nuevos, name='chat_mensajes_nuevos'),

    path('agentes/', views.panel_agente, name='panel_agente'),
    path('agentes/<int:conv_id>/', views.ver_chat, name='ver_chat'),
    path('agentes/<int:conv_id>/enviar/', views.enviar_mensaje_agente, name='chat_agente_enviar'),
    path('agentes/<int:conv_id>/mensajes/', views.mensajes_nuevos_agente, name='chat_agente_mensajes'),
    path('agentes/<int:conv_id>/accion/', views.accion_chat, name='accion_chat'),

    path('telegram/webhook/', views.telegram_webhook_chat, name='chat_telegram_webhook'),
]
