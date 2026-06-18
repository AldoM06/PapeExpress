import json
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import FiguraFomy, FotoFigura, HistorialEtapa, Libreta, ETAPAS
from .telegram import notificar_cambio_etapa
from .forms import FiguraFomyForm


def _ws_notify(figura):
    """Notifica cambio por WebSocket a todos los conectados."""
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'produccion',
            {
                'type': 'actualizacion_figura',
                'data': {
                    'tipo': 'actualizacion',
                    'figura': {
                        'id':            figura.id,
                        'nombre':        figura.nombre,
                        'etapa':         figura.etapa_actual,
                        'etapa_display': figura.get_etapa_actual_display(),
                        'color':         figura.color_etapa,
                        'porcentaje':    figura.porcentaje_avance,
                        'actualizado':   figura.actualizado.strftime('%d/%m/%Y %H:%M'),
                    }
                }
            }
        )
    except Exception:
        pass


@login_required
def lista_figuras(request):
    figuras = FiguraFomy.objects.prefetch_related('fotos').all()
    return render(request, 'produccion/lista_figuras.html', {
        'figuras': figuras,
        'etapas':  ETAPAS,
    })


@login_required
def detalle_figura(request, pk):
    figura   = get_object_or_404(FiguraFomy, pk=pk)
    historial = figura.historial.select_related('usuario').all()[:15]
    fotos    = figura.fotos.all()
    return render(request, 'produccion/detalle_figura.html', {
        'figura':   figura,
        'historial': historial,
        'etapas':   ETAPAS,
        'fotos':    fotos,
    })


@login_required
def crear_figura(request):
    form = FiguraFomyForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        figura = form.save()
        # Fotos (hasta 4)
        for f in request.FILES.getlist('fotos'):
            FotoFigura.objects.create(figura=figura, foto=f)
        messages.success(request, f'Figura "{figura.nombre}" creada correctamente.')
        return redirect('detalle_figura', pk=figura.pk)
    return render(request, 'produccion/form_figura.html', {'form': form, 'titulo': 'Nueva figura'})


@login_required
def editar_figura(request, pk):
    figura = get_object_or_404(FiguraFomy, pk=pk)
    form   = FiguraFomyForm(request.POST or None, request.FILES or None, instance=figura)
    if request.method == 'POST' and form.is_valid():
        form.save()
        # Nuevas fotos
        for f in request.FILES.getlist('fotos'):
            if figura.fotos.count() < 4:
                FotoFigura.objects.create(figura=figura, foto=f)
        messages.success(request, 'Figura actualizada.')
        return redirect('detalle_figura', pk=pk)
    return render(request, 'produccion/form_figura.html', {
        'form': form, 'figura': figura, 'titulo': f'Editar — {figura.nombre}'
    })


@login_required
@require_POST
def eliminar_foto(request, foto_pk):
    foto = get_object_or_404(FotoFigura, pk=foto_pk)
    figura_pk = foto.figura.pk
    # Eliminar archivo físico
    if foto.foto and os.path.isfile(foto.foto.path):
        os.remove(foto.foto.path)
    foto.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('detalle_figura', pk=figura_pk)


@login_required
@require_POST
def avanzar_etapa(request, pk):
    figura = get_object_or_404(FiguraFomy, pk=pk)
    etapas_lista = [e[0] for e in ETAPAS]
    nueva_etapa  = request.POST.get('etapa') or (
        etapas_lista[etapas_lista.index(figura.etapa_actual) + 1]
        if etapas_lista.index(figura.etapa_actual) < len(etapas_lista) - 1
        else figura.etapa_actual
    )
    notas = request.POST.get('notas', '')
    etapa_anterior = figura.etapa_actual

    HistorialEtapa.objects.create(
        figura=figura,
        etapa_anterior=etapa_anterior,
        etapa_nueva=nueva_etapa,
        usuario=request.user,
        notas=notas,
    )
    figura.etapa_actual = nueva_etapa
    figura.save()

    # WebSocket
    _ws_notify(figura)

    # Telegram
    notificar_cambio_etapa(figura, etapa_anterior, nueva_etapa, request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'etapa': figura.get_etapa_actual_display()})
    return redirect('detalle_figura', pk=pk)


@login_required
def eliminar_figura(request, pk):
    figura = get_object_or_404(FiguraFomy, pk=pk)
    if request.method == 'POST':
        nombre = figura.nombre
        figura.delete()
        messages.success(request, f'Figura "{nombre}" eliminada.')
        return redirect('lista_figuras')
    return render(request, 'produccion/confirmar_eliminar.html', {'figura': figura})
