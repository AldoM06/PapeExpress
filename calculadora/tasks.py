"""
Tarea de procesamiento de PDF en segundo plano.
Usa threading puro + Django Channels para enviar progreso por WebSocket.
No requiere Celery ni Redis adicional (usa el mismo channel layer del proyecto).
"""
import os
import time
import logging
import threading
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ── Tipos de hoja y precios ──────────────────────────────
TIPOS_HOJA = {
    'bond':       {'nombre': 'Bond / Carta',       'precio': .20},
    'fotografico':{'nombre': 'Fotográfico',         'precio': 10.0},
    'etiqueta':   {'nombre': 'Etiqueta',            'precio': 6.0},
    'opalina':    {'nombre': 'Opalina',             'precio': 2.5},
    'vinil':      {'nombre': 'Vinil',               'precio': 15.0},
    'couche':     {'nombre': 'Couché / Brillante',  'precio': 1.2},
}

UMBRAL_BLANCO = 248   # píxeles >= este valor en los 3 canales = blanco


def calcular_porcentaje_color(imagen: Image.Image) -> float:
    """Retorna el % de píxeles que NO son blancos (= tinta usada)."""
    try:
        arr = np.array(imagen.convert('RGB'))
        mascara_no_blanco = ~np.all(arr >= UMBRAL_BLANCO, axis=2)
        total = mascara_no_blanco.size
        coloreados = int(np.sum(mascara_no_blanco))
        return round((coloreados / total) * 100, 2) if total else 0.0
    except Exception as e:
        logger.error(f"Error calculando color: {e}")
        return 0.0


def enviar_progreso_ws(channel_name: str, data: dict):
    """Envía un mensaje al WebSocket del cliente (fire-and-forget)."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        layer = get_channel_layer()
        async_to_sync(layer.send)(channel_name, {
            'type': 'calculadora.progreso',
            **data,
        })
    except Exception as e:
        logger.warning(f"WS send error: {e}")


def procesar_pdf_tarea(
    filepath: str,
    filename: str,
    precio_minimo: float,
    precio_maximo: float,
    tipo_hoja: str,
    channel_name: str,
    usuario_id,
    ip_cliente: str,
    dpi: int = 80,
):
    """
    Procesamiento en hilo secundario.
    Convierte cada página a imagen, calcula % de color, estima costo.
    Envía actualizaciones de progreso por WebSocket al cliente.
    """
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'papeexpress.settings')

    start = time.time()
    resultados = []

    try:
        from pdf2image import convert_from_path

        # Detectar poppler según SO
        poppler_path = None
        import platform
        if platform.system() == 'Darwin':
            poppler_path = '/opt/homebrew/opt/poppler/bin'

        # Obtener total de páginas primero
        from pdf2image import pdfinfo_from_path
        try:
            info = pdfinfo_from_path(filepath, poppler_path=poppler_path)
            total_paginas = info.get('Pages', 0)
        except Exception:
            total_paginas = 0

        enviar_progreso_ws(channel_name, {
            'estado': 'iniciando',
            'mensaje': f'Procesando {filename}…',
            'progreso': 0,
            'total': total_paginas,
        })

        precio_hoja = TIPOS_HOJA.get(tipo_hoja, TIPOS_HOJA['bond'])['precio']

        # Convertir página por página para poder enviar progreso
        paginas = convert_from_path(
            filepath,
            dpi=dpi,
            fmt='jpeg',
            thread_count=2,
            poppler_path=poppler_path,
            use_pdftocairo=True,
            strict=False,
        )

        total_real = len(paginas)

        for i, pagina in enumerate(paginas):
            porcentaje = calcular_porcentaje_color(pagina)
            costo_color = precio_minimo + (precio_maximo - precio_minimo) * (porcentaje / 100)
            costo_total_pag = round(precio_hoja + costo_color, 2)

            resultados.append({
                'pagina':          i + 1,
                'porcentaje':      porcentaje,
                'tipo_hoja':       tipo_hoja,
                'precio_hoja':     precio_hoja,
                'costo_porcentaje': round(costo_color, 2),
                'costo':           costo_total_pag,
            })

            progreso = int(((i + 1) / total_real) * 100)
            enviar_progreso_ws(channel_name, {
                'estado':   'procesando',
                'progreso': progreso,
                'pagina_actual': i + 1,
                'total':    total_real,
                'ultimo_resultado': resultados[-1],
            })

        costo_total    = round(sum(r['costo'] for r in resultados), 2)
        costo_promedio = round(costo_total / total_real, 2) if total_real else 0
        tiempo         = round(time.time() - start, 2)

        # Guardar en historial
        try:
            from calculadora.models import HistorialCalculo
            from accounts.models import Usuario
            usuario = Usuario.objects.filter(pk=usuario_id).first() if usuario_id else None
            HistorialCalculo.objects.create(
                usuario=usuario,
                nombre_archivo=filename,
                num_paginas=total_real,
                tipo_hoja=tipo_hoja,
                precio_minimo=precio_minimo,
                precio_maximo=precio_maximo,
                costo_total=costo_total,
                costo_promedio=costo_promedio,
                tiempo_proceso=tiempo,
                ip_cliente=ip_cliente,
            )
        except Exception as e:
            logger.warning(f"No se pudo guardar historial: {e}")

        # Mensaje final
        enviar_progreso_ws(channel_name, {
            'estado':        'completado',
            'progreso':      100,
            'resultados':    resultados,
            'costo_total':   costo_total,
            'costo_promedio': costo_promedio,
            'tiempo':        tiempo,
            'total':         total_real,
        })

    except Exception as e:
        logger.error(f"Error en tarea PDF: {e}", exc_info=True)
        enviar_progreso_ws(channel_name, {
            'estado':  'error',
            'mensaje': str(e),
            'progreso': 0,
        })
    finally:
        try:
            os.remove(filepath)
        except Exception:
            pass


def lanzar_tarea(kwargs: dict):
    """Lanza procesar_pdf_tarea en un hilo daemon."""
    t = threading.Thread(target=procesar_pdf_tarea, kwargs=kwargs, daemon=True)
    t.start()
    return t
