from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/', views.productos_view, name='productos'),
    path('nosotros/', views.nosotros_view, name='nosotros'),
    path('contacto/', views.contacto_view, name='contacto'),
]
