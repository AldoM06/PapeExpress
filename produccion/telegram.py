"""
Servicio de notificaciones a Telegram.
Configuración en settings.py:
  TELEGRAM_BOT_TOKEN = 'tu_token_aqui'
  TELEGRAM_CHAT_ID   = 'tu_chat_id_aqui'  # puede ser un grupo o canal
"""
import logging
import threading
import urllib.request
import urllib.parse
import json
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ETAPA_EMOJIS = {
    'propuesta':      '💡',
    'diseño':         '✏️',
    'armado_digital': '💻',
    'muestra':        '🔍',
    'materiales':     '📦',
    'corte':          '✂️',
    'armado':         '🔧',
    'embolsado':      '🛍️',
    'etiquetado':     '🏷️',
    'terminado':      '✅',
}


def _api_post(endpoint: str, payload: dict) -> dict:
    """POST genérico a la Bot API de Telegram. Retorna el JSON de respuesta."""
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        logger.warning('TELEGRAM_BOT_TOKEN no configurado.')
        return {}
    url = f'https://api.telegram.org/bot{token}/{endpoint}'
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            if not result.get('ok'):
                logger.error(f'Telegram API error [{endpoint}]: {result}')
            return result
    except Exception as e:
        logger.error(f'Error llamando Telegram [{endpoint}]: {e}')
        return {}


def _enviar(mensaje: str):
    """Envía mensaje de texto al chat configurado."""
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        logger.warning('TELEGRAM_CHAT_ID no configurado.')
        return False
    result = _api_post('sendMessage', {
        'chat_id': chat_id,
        'text': mensaje,
        'parse_mode': 'HTML',
    })
    return result.get('ok', False)


def _enviar_foto_con_botones(foto_path: str, caption: str, inline_keyboard: list):
    """
    Envía una foto al chat con botones inline, subiendo el archivo directamente
    (multipart) en lugar de pasar una URL — así funciona aunque el sitio
    no sea públicamente accesible para Telegram.
    """
    token   = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        logger.warning('Telegram no configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).')
        return False

    url = f'https://api.telegram.org/bot{token}/sendPhoto'
    try:
        with open(foto_path, 'rb') as f:
            resp = requests.post(
                url,
                data={
                    'chat_id': chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML',
                    'reply_markup': json.dumps({'inline_keyboard': inline_keyboard}),
                },
                files={'photo': f},
                timeout=15,
            )
        result = resp.json()
        if not result.get('ok'):
            logger.error(f'Telegram sendPhoto error: {result}')
        return result.get('ok', False)
    except Exception as e:
        logger.error(f'Error enviando foto a Telegram: {e}')
        return False


def editar_mensaje_callback(chat_id: str, message_id: int, nuevo_texto: str):
    """Edita el caption de un mensaje foto tras responder un callback."""
    _api_post('editMessageCaption', {
        'chat_id': chat_id,
        'message_id': message_id,
        'caption': nuevo_texto,
        'parse_mode': 'HTML',
        'reply_markup': {'inline_keyboard': []},
    })


def responder_callback(callback_query_id: str, texto: str):
    """Responde al callback para quitar el spinner en Telegram."""
    _api_post('answerCallbackQuery', {
        'callback_query_id': callback_query_id,
        'text': texto,
        'show_alert': False,
    })


def enviar_async(mensaje: str):
    """Lanza _enviar en hilo daemon para no bloquear el request."""
    t = threading.Thread(target=_enviar, args=(mensaje,), daemon=True)
    t.start()


# ── Mensajes predefinidos ──────────────────────────────────

def notificar_cambio_etapa(figura, etapa_anterior, etapa_nueva, usuario=None):
    emoji_ant = ETAPA_EMOJIS.get(etapa_anterior, '▪️')
    emoji_nva = ETAPA_EMOJIS.get(etapa_nueva, '▪️')
    quien = usuario.get_full_name() or usuario.username if usuario else 'Sistema'

    msg = (
        f"🎨 <b>PaPeExpress — Producción</b>\n\n"
        f"La figura <b>{figura.nombre}</b> avanzó de etapa:\n\n"
        f"{emoji_ant} <s>{figura.get_etapa_display_for(etapa_anterior)}</s>\n"
        f"↓\n"
        f"{emoji_nva} <b>{figura.get_etapa_display_for(etapa_nueva)}</b>\n\n"
        f"👤 Actualizado por: {quien}\n"
        f"📊 Avance: {figura.porcentaje_avance}%\n"
        f"🔢 Cantidad planificada: {figura.cantidad_planificada} pzas"
    )
    enviar_async(msg)


def notificar_nuevo_pedido(pedido):
    msg = (
        f"🛒 <b>PaPeExpress — Nuevo pedido</b>\n\n"
        f"Socio: <b>{pedido.socio.nombre}</b>\n"
        f"Figura: <b>{pedido.figura.nombre}</b>\n"
        f"Cantidad: <b>{pedido.cantidad} pzas</b>\n"
        f"Total: <b>${pedido.total}</b>\n"
        f"Estado: {pedido.get_estado_display()}"
    )
    enviar_async(msg)


def notificar_nueva_cotizacion(cotizacion):
    detalles = cotizacion.detalles.select_related('producto').all()
    lineas = '\n'.join(
        f"  • {d.cantidad}x {d.producto.nombre} "
        f"({d.producto.peso} kg c/u) — ${d.subtotal}"
        for d in detalles
    )
    cliente = cotizacion.cliente
    nombre = cliente.get_full_name() or cliente.username
    # Info de envío
    metodo_label = dict(cotizacion.METODO_ENVIO).get(cotizacion.metodo_envio, cotizacion.metodo_envio)
    if cotizacion.metodo_envio == 'recoger':
        envio_txt = '🏪 Recoger en tienda'
    else:
        partes = filter(None, [
            cotizacion.direccion_calle, cotizacion.direccion_colonia,
            cotizacion.direccion_ciudad, cotizacion.direccion_estado,
            cotizacion.direccion_cp,
        ])
        envio_txt = (
            f"🚚 {metodo_label}\n"
            f"   📍 {', '.join(partes) or 'Sin dirección'}\n"
            f"   💲 Costo envío: ${cotizacion.costo_envio}"
        )
    fecha_req = cotizacion.fecha_requerida
    if hasattr(fecha_req, 'strftime'):
        fecha_txt = fecha_req.strftime('%d/%m/%Y')
    elif fecha_req:
        fecha_txt = str(fecha_req)
    else:
        fecha_txt = 'Sin fecha límite'

    msg = (
        f"📋 <b>PaPeExpress — Nueva Cotización #{cotizacion.id}</b>\n\n"
        f"👤 Cliente: <b>{nombre}</b>\n"
        f"📞 Tel: {cliente.telefono or 'No registrado'}\n"
        f"📧 Email: {cliente.email}\n\n"
        f"<b>Productos:</b>\n{lineas}\n\n"
        f"⚖️ Peso total: <b>{cotizacion.peso_total} kg</b>\n"
        f"💰 Subtotal estimado: <b>${cotizacion.total_estimado}</b>\n\n"
        f"<b>Envío:</b>\n{envio_txt}\n"
        f"📅 Fecha requerida: {fecha_txt}\n"
        f"📝 Notas entrega: {cotizacion.notas_entrega or '—'}\n\n"
        f"🗒 Notas generales: {cotizacion.notas or '—'}"
    )
    enviar_async(msg)


def notificar_verificacion_pendiente(usuario):
    """Envía la foto del negocio al grupo con botones Aprobar / Rechazar."""
    nombre = usuario.get_full_name() or usuario.username
    caption = (
        f"🏪 <b>PaPeExpress — Verificación de negocio</b>\n\n"
        f"👤 <b>{nombre}</b> solicita ser verificado como cliente.\n"
        f"📞 Tel: {usuario.telefono or 'No registrado'}\n"
        f"📧 Email: {usuario.email}\n"
        f"🏢 Empresa: {usuario.empresa or 'No registrada'}\n\n"
        f"¿Apruebas este negocio como cliente PapeExpress?"
    )
    keyboard = [[
        {'text': '✅ Aprobar', 'callback_data': f'verif_aprobar_{usuario.id}'},
        {'text': '❌ Rechazar', 'callback_data': f'verif_rechazar_{usuario.id}'},
    ]]

    t = threading.Thread(
        target=_enviar_foto_con_botones,
        args=(usuario.foto_negocio.path, caption, keyboard),
        daemon=True,
    )
    t.start()


def notificar_pago_confirmado(pedido):
    msg = (
        f"💳 <b>PaPeExpress — Pago confirmado ✅</b>\n\n"
        f"Socio: <b>{pedido.socio.nombre}</b>\n"
        f"Figura: <b>{pedido.figura.nombre}</b>\n"
        f"Cantidad: <b>{pedido.cantidad} pzas</b>\n"
        f"Total pagado: <b>${pedido.total}</b>\n\n"
        f"El inventario se ha actualizado automáticamente."
    )
    enviar_async(msg)
