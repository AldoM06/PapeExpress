import os
import uuid
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings

from .tasks import lanzar_tarea, TIPOS_HOJA
from .models import HistorialCalculo, PlanCalculadora

logger = logging.getLogger(__name__)

# ── Límites según plan ───────────────────────────────────
LIMITES_DEFAULT = {
    None:        {'max_mb': 5,    'max_paginas': 20,  'label': 'Visitante'},
    'cliente':   {'max_mb': 15,   'max_paginas': 80,  'label': 'Cliente'},
    'socio':     {'max_mb': 50,   'max_paginas': 300, 'label': 'Socio'},
    'ventas':    {'max_mb': 50,   'max_paginas': 300, 'label': 'Ventas'},
    'almacen':   {'max_mb': 50,   'max_paginas': 300, 'label': 'Almacén'},
    'diseño':    {'max_mb': 100,  'max_paginas': 500, 'label': 'Diseño'},
    'produccion':{'max_mb': 100,  'max_paginas': 500, 'label': 'Producción'},
    'admin':     {'max_mb': 500,  'max_paginas': 9999,'label': 'Admin'},
}

PRECIO_MIN_DEFAULT = 1.0
PRECIO_MAX_DEFAULT = 8.0


def _get_limite(user):
    """Devuelve el límite correspondiente al usuario actual."""
    if not user or not user.is_authenticated:
        return LIMITES_DEFAULT[None]
    if user.is_superuser or user.rol == 'admin':
        return LIMITES_DEFAULT['admin']
    return LIMITES_DEFAULT.get(user.rol, LIMITES_DEFAULT['cliente'])


def calculadora_view(request):
    """Vista principal de la calculadora (acceso libre con límites reducidos)."""
    user = request.user if request.user.is_authenticated else None
    limite = _get_limite(user)
    historial = []
    if user:
        historial = HistorialCalculo.objects.filter(usuario=user).order_by('-creado')[:10]

    return render(request, 'calculadora/calculadora.html', {
        'tipos_hoja': TIPOS_HOJA,
        'precio_min': PRECIO_MIN_DEFAULT,
        'precio_max': PRECIO_MAX_DEFAULT,
        'limite': limite,
        'historial': historial,
        'es_autenticado': user is not None,
    })


@require_POST
def subir_pdf(request):
    """
    Recibe el PDF, valida tamaño/tipo, lanza la tarea en segundo plano
    y responde JSON con el job_id para que el cliente monitoree por WS.
    """
    user = request.user if request.user.is_authenticated else None
    limite = _get_limite(user)

    # ── Validar archivo ──────────────────────────────────
    if 'pdf' not in request.FILES:
        return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

    archivo = request.FILES['pdf']

    if not archivo.name.lower().endswith('.pdf'):
        return JsonResponse({'error': 'Solo se aceptan archivos PDF.'}, status=400)

    # Validar tamaño
    tam_mb = archivo.size / (1024 * 1024)
    if tam_mb > limite['max_mb']:
        return JsonResponse({
            'error': f'Tu plan ({limite["label"]}) permite archivos de hasta {limite["max_mb"]} MB. '
                     f'Este archivo pesa {tam_mb:.1f} MB. Inicia sesión o contacta a PaPeExpress para ampliar tu límite.'
        }, status=400)

    # ── Parámetros de cálculo ────────────────────────────
    try:
        precio_min = float(request.POST.get('precio_minimo', PRECIO_MIN_DEFAULT))
        precio_max = float(request.POST.get('precio_maximo', PRECIO_MAX_DEFAULT))
    except ValueError:
        return JsonResponse({'error': 'Los precios deben ser números válidos.'}, status=400)

    if precio_min < 0 or precio_max < 0:
        return JsonResponse({'error': 'Los precios no pueden ser negativos.'}, status=400)
    if precio_max < precio_min:
        return JsonResponse({'error': 'El precio máximo debe ser mayor al mínimo.'}, status=400)

    tipo_hoja = request.POST.get('tipo_hoja', 'bond')
    channel_name = request.POST.get('channel_name', '')

    if not channel_name:
        return JsonResponse({'error': 'Conexión WebSocket no establecida. Recarga la página.'}, status=400)

    # ── Guardar archivo temporal ─────────────────────────
    upload_dir = os.path.join(settings.MEDIA_ROOT, 'calc_tmp')
    os.makedirs(upload_dir, exist_ok=True)
    ext = '.pdf'
    tmp_name = f'{uuid.uuid4().hex}{ext}'
    filepath = os.path.join(upload_dir, tmp_name)

    with open(filepath, 'wb') as f:
        for chunk in archivo.chunks():
            f.write(chunk)

    # ── Lanzar tarea en segundo plano ───────────────────
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    lanzar_tarea({
        'filepath':     filepath,
        'filename':     archivo.name,
        'precio_minimo': precio_min,
        'precio_maximo': precio_max,
        'tipo_hoja':    tipo_hoja,
        'channel_name': channel_name,
        'usuario_id':   user.pk if user else None,
        'ip_cliente':   ip,
    })

    return JsonResponse({'ok': True, 'mensaje': 'Procesamiento iniciado.'})


@login_required
def historial_view(request):
    """Historial personal del usuario autenticado."""
    calculos = HistorialCalculo.objects.filter(usuario=request.user).order_by('-creado')
    return render(request, 'calculadora/historial.html', {'calculos': calculos})


@login_required
def historial_admin_view(request):
    """Vista de todos los cálculos (solo admin)."""
    if not (request.user.is_superuser or request.user.rol == 'admin'):
        return redirect('calculadora')
    calculos = HistorialCalculo.objects.select_related('usuario').order_by('-creado')[:200]
    return render(request, 'calculadora/historial_admin.html', {'calculos': calculos})
