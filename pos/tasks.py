"""
Tareas programadas del POS:
  - Alerta inmediata cuando un producto llega al mínimo
  - Barrido diario al mediodía de todos los productos críticos
  - Comparación de precios entre proveedores

Para el barrido al mediodía usa APScheduler (ya incluido).
Alternativa: cron job que llame /pos/api/barrido-inventario/ con token.
"""
import logging
import threading
from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler_iniciado = False


# ── Alerta inmediata de stock mínimo ─────────────────────
def alerta_stock_minimo(inventario):
    """Llamar después de cada movimiento de salida."""
    if not inventario.bajo_minimo:
        return
    from produccion.telegram import enviar_async
    msg = (
        f"⚠️ <b>PaPeExpress POS — Stock mínimo alcanzado</b>\n\n"
        f"📦 Producto: <b>{inventario.producto.nombre}</b>\n"
        f"🏪 Sucursal: <b>{inventario.sucursal.nombre}</b>\n"
        f"📉 Stock actual: <b>{inventario.stock_actual} {inventario.producto.unidad}</b>\n"
        f"🔴 Mínimo configurado: <b>{inventario.stock_minimo} {inventario.producto.unidad}</b>\n\n"
        f"⚡ Es momento de hacer un pedido al proveedor."
    )
    enviar_async(msg)


# ── Barrido al mediodía ───────────────────────────────────
def barrido_inventario_critico():
    """Escanea todos los productos bajo mínimo y manda resumen."""
    try:
        from pos.models import Inventario
        from produccion.telegram import enviar_async

        criticos = Inventario.objects.filter(
            stock_actual__lte=models.F('stock_minimo'),
            stock_minimo__gt=0,
            sucursal__activa=True,
        ).select_related('producto', 'sucursal').order_by('sucursal__nombre', 'producto__nombre')

        # Import aquí para evitar circular
        from django.db import models

        criticos = Inventario.objects.select_related('producto', 'sucursal').filter(
            stock_minimo__gt=0,
            sucursal__activa=True,
        )
        criticos = [i for i in criticos if i.bajo_minimo]

        if not criticos:
            return

        lineas = []
        sucursal_actual = None
        for inv in sorted(criticos, key=lambda x: (x.sucursal.nombre, x.producto.nombre)):
            if inv.sucursal.nombre != sucursal_actual:
                sucursal_actual = inv.sucursal.nombre
                lineas.append(f'\n🏪 <b>{sucursal_actual}</b>')
            lineas.append(
                f'  • {inv.producto.nombre}: '
                f'<b>{inv.stock_actual}</b>/{inv.stock_minimo} {inv.producto.unidad}'
            )

        msg = (
            f"📊 <b>PaPeExpress — Reporte mediodía</b>\n"
            f"🕛 {timezone.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"⚠️ <b>{len(criticos)} productos por agotarse:</b>\n"
            + '\n'.join(lineas)
        )
        enviar_async(msg)
        logger.info(f'Barrido inventario: {len(criticos)} productos críticos notificados.')

    except Exception as e:
        logger.error(f'Error en barrido_inventario_critico: {e}')


# ── Programar con APScheduler ─────────────────────────────
def iniciar_scheduler():
    global _scheduler_iniciado
    if _scheduler_iniciado:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(timezone='America/Mexico_City')
        scheduler.add_job(
            barrido_inventario_critico,
            CronTrigger(hour=12, minute=0),
            id='barrido_mediadia',
            replace_existing=True,
        )
        scheduler.start()
        _scheduler_iniciado = True
        logger.info('Scheduler POS iniciado — barrido diario a las 12:00')
    except ImportError:
        logger.warning('APScheduler no instalado. Instala: pip install apscheduler')
    except Exception as e:
        logger.error(f'Error iniciando scheduler: {e}')


# Iniciar en hilo daemon al importar (Django ready)
threading.Thread(target=iniciar_scheduler, daemon=True).start()
