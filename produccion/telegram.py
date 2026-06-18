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


def _enviar(mensaje: str):
    """Envía mensaje a Telegram (blocking, llamar desde hilo)."""
    token   = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')

    if not token or not chat_id:
        logger.warning('Telegram no configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).')
        return False

    url  = f'https://api.telegram.org/bot{token}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id':    chat_id,
        'text':       mensaje,
        'parse_mode': 'HTML',
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            if not result.get('ok'):
                logger.error(f'Telegram API error: {result}')
                return False
        return True
    except Exception as e:
        logger.error(f'Error enviando a Telegram: {e}')
        return False


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
