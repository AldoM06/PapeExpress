from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/', views.productos_view, name='productos'),
    path('productos/<int:pk>/', views.producto_detalle, name='producto_detalle'),
    path('nosotros/', views.nosotros_view, name='nosotros'),
    path('contacto/', views.contacto_view, name='contacto'),
    path('socios/presentacion/', views.presentacion_socios, name='presentacion_socios'),
]
