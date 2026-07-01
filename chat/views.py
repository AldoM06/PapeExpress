import json
import threading
from datetime import datetime, timezone as tz

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Conversacion, Mensaje


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_conv_anonimo(request):
    """Recupera la conversación activa de un visitante anónimo por sesión."""
    conv_id = request.session.get('chat_conv_id')
    if conv_id:
        return Conversacion.objects.filter(pk=conv_id, estado__in=['abierta', 'atendida']).first()
    return None


# ── Iniciar chat ──────────────────────────────────────────────────────────────

@ensure_csrf_cookie
def iniciar_chat(request):
    """Punto de entrada al chat — muestra el widget embebido (no página completa)."""
    if request.user.is_authenticated:
        conv = Conversacion.objects.filter(
            cliente=request.user, estado__in=['abierta', 'atendida']
        ).first()
        if not conv:
            conv = Conversacion.objects.create(cliente=request.user)
            Mensaje.objects.create(
                conversacion=conv, origen='sistema',
                texto='¡Hola! ¿En qué podemos ayudarte? Un asesor responderá en breve.',
            )
        return render(request, 'chat/chat_cliente.html', {
            'conv': conv,
            'historial': conv.mensajes.all(),
        })
    else:
        # Anónimo: verificar si ya tiene sesión activa
        conv = _get_conv_anonimo(request)
        if conv:
            return render(request, 'chat/chat_cliente.html', {
                'conv': conv,
                'historial': conv.mensajes.all(),
            })
        # Sin sesión: mostrar formulario de datos
        return render(request, 'chat/chat_cliente.html', {'conv': None})


@require_POST
def iniciar_anonimo(request):
    """Crea conversación para visitante anónimo con sus datos de contacto."""
    nombre   = request.POST.get('nombre', '').strip()
    telefono = request.POST.get('telefono', '').strip()
    email    = request.POST.get('email', '').strip()

    if not nombre:
        return JsonResponse({'ok': False, 'error': 'El nombre es requerido.'}, status=400)

    conv = Conversacion.objects.create(
        visitante_nombre=nombre,
        visitante_telefono=telefono,
        visitante_email=email,
    )
    Mensaje.objects.create(
        conversacion=conv, origen='sistema',
        texto=f'¡Hola {nombre}! ¿En qué podemos ayudarte? Un asesor responderá en breve.',
    )
    request.session['chat_conv_id'] = conv.id

    request.session.save()  # forzar guardado antes de responder
    historial = list(conv.mensajes.values('origen', 'texto', 'enviado'))
    return JsonResponse({
        'ok': True,
        'conv_id': conv.id,
        'mensajes': [
            {'origen': m['origen'], 'texto': m['texto'], 'hora': m['enviado'].strftime('%H:%M')}
            for m in historial
        ],
    })


# ── Mensajes cliente ──────────────────────────────────────────────────────────

@require_POST
def enviar_mensaje_cliente(request):
    texto   = request.POST.get('texto', '').strip()
    conv_id = request.POST.get('conv_id')
    if not texto or not conv_id:
        return JsonResponse({'ok': False}, status=400)

    # Verificar acceso
    if request.user.is_authenticated:
        conv = get_object_or_404(Conversacion, pk=conv_id, cliente=request.user)
    else:
        session_conv_id = request.session.get('chat_conv_id')
        if str(session_conv_id) != str(conv_id):
            return JsonResponse({'ok': False}, status=403)
        conv = get_object_or_404(Conversacion, pk=conv_id)

    if conv.estado == 'cerrada':
        return JsonResponse({'ok': False, 'error': 'Chat cerrado'}, status=400)

    msg = Mensaje.objects.create(conversacion=conv, origen='cliente', texto=texto)
    nombre = conv.nombre_contacto()

    conv_id_int     = conv.id
    tg_msg_id_actual = conv.telegram_msg_id

    def _notificar():
        import logging
        logger = logging.getLogger(__name__)
        try:
            from produccion.telegram import notificar_mensaje_chat
            from .models import Conversacion as Conv
            conv_obj = Conv.objects.get(pk=conv_id_int)
            msg_id = notificar_mensaje_chat(conv_obj, texto, nombre)
            if msg_id and not tg_msg_id_actual:
                Conv.objects.filter(pk=conv_id_int).update(telegram_msg_id=msg_id)
        except Exception as e:
            logger.error(f'Error notificando Telegram en chat #{conv_id_int}: {e}')

    threading.Thread(target=_notificar, daemon=True).start()

    return JsonResponse({
        'ok': True,
        'msg': {'origen': 'cliente', 'texto': texto, 'hora': msg.enviado.strftime('%H:%M')},
    })


def mensajes_nuevos(request, conv_id):
    """Polling del cliente: devuelve mensajes nuevos desde ?desde=<timestamp_ms>."""
    if request.user.is_authenticated:
        conv = get_object_or_404(Conversacion, pk=conv_id, cliente=request.user)
    else:
        session_conv_id = request.session.get('chat_conv_id')
        if str(session_conv_id) != str(conv_id):
            return JsonResponse({'ok': False}, status=403)
        conv = get_object_or_404(Conversacion, pk=conv_id)

    desde_ms = int(request.GET.get('desde', 0) or 0)
    desde_dt = datetime.fromtimestamp(desde_ms / 1000, tz=tz.utc)
    msgs = conv.mensajes.filter(enviado__gt=desde_dt).order_by('enviado')

    return JsonResponse({
        'estado': conv.estado,
        'mensajes': [
            {'origen': m.origen, 'texto': m.texto, 'hora': m.enviado.strftime('%H:%M')}
            for m in msgs
        ],
    })


# ── Panel agente ──────────────────────────────────────────────────────────────

@staff_member_required
def panel_agente(request):
    abiertas  = Conversacion.objects.filter(estado='abierta').select_related('cliente')
    atendidas = Conversacion.objects.filter(estado='atendida').select_related('cliente', 'agente')
    cerradas  = Conversacion.objects.filter(estado='cerrada').select_related('cliente', 'agente')[:20]
    return render(request, 'chat/panel_agente.html', {
        'abiertas': abiertas, 'atendidas': atendidas, 'cerradas': cerradas,
    })


@staff_member_required
def ver_chat(request, conv_id):
    conv = get_object_or_404(Conversacion, pk=conv_id)
    if conv.estado == 'abierta':
        conv.estado = 'atendida'
        conv.agente = request.user
        conv.save(update_fields=['estado', 'agente'])
    return render(request, 'chat/chat_agente.html', {
        'conv': conv,
        'historial': conv.mensajes.all(),
    })


@staff_member_required
@require_POST
def enviar_mensaje_agente(request, conv_id):
    conv  = get_object_or_404(Conversacion, pk=conv_id)
    texto = request.POST.get('texto', '').strip()
    if not texto:
        return JsonResponse({'ok': False}, status=400)
    if conv.agente is None:
        conv.agente = request.user
        conv.estado = 'atendida'
        conv.save(update_fields=['agente', 'estado'])
    msg = Mensaje.objects.create(conversacion=conv, origen='agente', texto=texto)
    return JsonResponse({
        'ok': True,
        'msg': {
            'origen': 'agente', 'texto': texto, 'hora': msg.enviado.strftime('%H:%M'),
            'nombre': request.user.get_full_name() or request.user.username,
        },
    })


@staff_member_required
def mensajes_nuevos_agente(request, conv_id):
    conv = get_object_or_404(Conversacion, pk=conv_id)
    desde_ms = int(request.GET.get('desde', 0) or 0)
    desde_dt = datetime.fromtimestamp(desde_ms / 1000, tz=tz.utc)
    msgs = conv.mensajes.filter(enviado__gt=desde_dt).order_by('enviado')
    return JsonResponse({
        'mensajes': [
            {'origen': m.origen, 'texto': m.texto, 'hora': m.enviado.strftime('%H:%M')}
            for m in msgs
        ],
    })


@staff_member_required
@require_POST
def accion_chat(request, conv_id):
    conv = get_object_or_404(Conversacion, pk=conv_id)
    if request.POST.get('accion') == 'cerrar':
        conv.estado  = 'cerrada'
        conv.cerrada = timezone.now()
        conv.save(update_fields=['estado', 'cerrada'])
    return redirect('panel_agente')


# ── Webhook Telegram ──────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def telegram_webhook_chat(request):
    from django.conf import settings
    token_param = request.GET.get('token', '')
    bot_token   = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or token_param != bot_token[-10:]:
        return JsonResponse({'ok': False}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    message    = data.get('message', {})
    reply_to   = message.get('reply_to_message', {})
    if not reply_to:
        return JsonResponse({'ok': True})

    replied_msg_id = reply_to.get('message_id')
    texto          = message.get('text', '').strip()
    from_user      = message.get('from', {})
    nombre_agente  = (
        f"{from_user.get('first_name','')} {from_user.get('last_name','')}".strip()
        or from_user.get('username', 'Agente')
    )

    if texto and replied_msg_id:
        conv = Conversacion.objects.filter(telegram_msg_id=replied_msg_id).first()
        if conv and conv.estado != 'cerrada':
            Mensaje.objects.create(
                conversacion=conv, origen='agente',
                texto=f"{nombre_agente}: {texto}",
            )
    return JsonResponse({'ok': True})
