from django.urls import path
from . import views

urlpatterns = [
    path('figuras/',                    views.lista_figuras,   name='lista_figuras'),
    path('figuras/nueva/',              views.crear_figura,    name='crear_figura'),
    path('figuras/<int:pk>/',           views.detalle_figura,  name='detalle_figura'),
    path('figuras/<int:pk>/editar/',    views.editar_figura,   name='editar_figura'),
    path('figuras/<int:pk>/avanzar/',   views.avanzar_etapa,   name='avanzar_etapa'),
    path('figuras/<int:pk>/eliminar/',  views.eliminar_figura, name='eliminar_figura'),
    path('fotos/<int:foto_pk>/eliminar/', views.eliminar_foto, name='eliminar_foto'),
]
