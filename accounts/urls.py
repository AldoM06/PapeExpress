from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/', views.registro_view, name='registro'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/admin/', views.dashboard_admin, name='dashboard_admin'),
    path('dashboard/cliente/', views.dashboard_cliente, name='dashboard_cliente'),
    path('dashboard/socio/', views.dashboard_socio, name='dashboard_socio'),
    path('dashboard/ventas/', views.dashboard_ventas, name='dashboard_ventas'),
    path('dashboard/almacen/', views.dashboard_almacen, name='dashboard_almacen'),
    path('dashboard/produccion/', views.dashboard_produccion, name='dashboard_produccion'),
]
