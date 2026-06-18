from django.urls import path
from . import views

urlpatterns = [
    path('',           views.calculadora_view,      name='calculadora'),
    path('subir/',     views.subir_pdf,             name='calc_subir'),
    path('historial/', views.historial_view,         name='calc_historial'),
    path('historial/admin/', views.historial_admin_view, name='calc_historial_admin'),
]
