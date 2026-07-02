"""
Servicios de negocio del POS:
 - Crear venta y descontar inventario
 - Registrar compra y actualizar costo promedio
 - Analizar ticket con IA (Anthropic Claude)
 - Comparar precios entre proveedores
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from .models import (
    Venta, DetalleVenta, Inventario, MovimientoInventario,
    CompraProveedor, DetalleCompra, PrecioHistoricoProveedor,
    ConfigPOS,
)
from .tasks import alerta_stock_minimo

logger = logging.getLogger(__name__)


# ── VENTA ─────────────────────────────────────────────────

@transaction.atomic
def crear_venta(sucursal, cajero, items, forma_pago='efectivo',
                total_pagado=None, notas=''):
    """
    items = [{'producto': obj, 'cantidad': 2, 'precio': 15.00,
               'costo': 8.00, 'nivel': 1, 'descuento': 0}, ...]
    """
    # Validar stock disponible antes de crear nada
    for item in items:
        prod     = item['producto']
        cantidad = Decimal(str(item['cantidad']))
        inv = Inventario.objects.filter(producto=prod, sucursal=sucursal).first()
        stock_disponible = inv.stock_actual if inv else Decimal('0')
        if stock_disponible < cantidad:
            raise ValueError(
                f'Stock insuficiente para "{prod.nombre}": '
                f'disponible {stock_disponible} {prod.unidad}, solicitado {cantidad}.'
            )

    venta = Venta.objects.create(
        sucursal=sucursal,
        cajero=cajero,
        forma_pago=forma_pago,
        notas=notas,
        estado='pagada' if forma_pago != 'credito' else 'credito',
    )

    subtotal = Decimal('0')
    costo_total = Decimal('0')

    for item in items:
        prod     = item['producto']
        cantidad = Decimal(str(item['cantidad']))
        precio   = Decimal(str(item['precio']))
        costo    = Decimal(str(item.get('costo', 0)))
        descuento = Decimal(str(item.get('descuento', 0)))

        DetalleVenta.objects.create(
            venta=venta, producto=prod,
            cantidad=cantidad, precio_unitario=precio,
            costo_unitario=costo, descuento=descuento,
            nivel_precio=item.get('nivel', 1),
        )
        subtotal    += precio * cantidad
        costo_total += costo * cantidad

        # Descontar inventario
        inv, _ = Inventario.objects.get_or_create(
            producto=prod, sucursal=sucursal,
            defaults={'stock_actual': 0, 'costo_promedio': costo},
        )
        stock_antes = inv.stock_actual
        inv.stock_actual = max(Decimal('0'), inv.stock_actual - cantidad)
        inv.save()

        MovimientoInventario.objects.create(
            inventario=inv, tipo='salida',
            cantidad=cantidad, stock_antes=stock_antes,
            stock_despues=inv.stock_actual,
            costo_unitario=costo,
            referencia=f'Venta {venta.folio}',
            usuario=cajero,
        )
        # Alerta si llegó al mínimo
        alerta_stock_minimo(inv)

    venta.subtotal    = subtotal
    venta.costo_total = costo_total
    venta.total       = subtotal
    venta.total_pagado = Decimal(str(total_pagado)) if total_pagado is not None else subtotal
    venta.save()
    return venta


# ── COMPRA / ENTRADA DE MERCANCÍA ─────────────────────────

@transaction.atomic
def registrar_compra(proveedor, sucursal, usuario, items,
                     folio='', fecha=None, ticket_imagen=None, notas=''):
    """
    items = [{'producto': obj, 'cantidad': 10, 'costo': 5.50}, ...]
    Actualiza costo promedio ponderado y registra historial de precios.
    """
    compra = CompraProveedor.objects.create(
        proveedor=proveedor, sucursal=sucursal,
        folio=folio, fecha_compra=fecha or timezone.now().date(),
        ticket_imagen=ticket_imagen,
        usuario=usuario, notas=notas,
        estado='recibida',
    )

    total = Decimal('0')
    for item in items:
        prod     = item['producto']
        cantidad = Decimal(str(item['cantidad']))
        costo    = Decimal(str(item['costo']))
        subtotal = cantidad * costo

        DetalleCompra.objects.create(
            compra=compra, producto=prod,
            cantidad=cantidad, costo_unitario=costo,
        )
        total += subtotal

        # Actualizar inventario con costo promedio ponderado
        inv, _ = Inventario.objects.get_or_create(
            producto=prod, sucursal=sucursal,
            defaults={'stock_actual': 0, 'costo_promedio': costo},
        )
        stock_antes = inv.stock_actual
        stock_nuevo = inv.stock_actual + cantidad

        # Costo promedio ponderado
        if stock_nuevo > 0:
            inv.costo_promedio = (
                (inv.stock_actual * inv.costo_promedio) + (cantidad * costo)
            ) / stock_nuevo

        inv.stock_actual = stock_nuevo
        inv.save()

        MovimientoInventario.objects.create(
            inventario=inv, tipo='entrada',
            cantidad=cantidad, stock_antes=stock_antes,
            stock_despues=stock_nuevo,
            costo_unitario=costo,
            referencia=f'Compra {compra.pk} | {proveedor.nombre}',
            usuario=usuario, compra=compra,
        )

        # Historial de precios del proveedor
        PrecioHistoricoProveedor.objects.create(
            proveedor=proveedor, producto=prod,
            costo=costo, fecha=compra.fecha_compra,
            compra=compra,
        )

    compra.total = total
    compra.save()
    return compra


# ── ANÁLISIS DE TICKET CON IA ─────────────────────────────

def analizar_ticket_ia(imagen_path: str = None, texto_ticket: str = None) -> dict:
    """
    Analiza un ticket de proveedor usando Claude API.
    Retorna: {'proveedor': str, 'fecha': str, 'items': [...], 'total': float}
    """
    import os, base64, json, urllib.request, urllib.parse

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY no configurada en .env'}

    messages = []

    if imagen_path and os.path.isfile(imagen_path):
        with open(imagen_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = imagen_path.rsplit('.', 1)[-1].lower()
        media_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                      'png': 'image/png', 'pdf': 'application/pdf'}.get(ext, 'image/jpeg')
        messages.append({
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': img_b64}},
                {'type': 'text', 'text': (
                    'Analiza este ticket/factura de proveedor y extrae la información en JSON. '
                    'Responde SOLO con JSON válido, sin markdown, con esta estructura: '
                    '{"proveedor": "nombre del proveedor", "fecha": "YYYY-MM-DD", '
                    '"folio": "número de ticket", "items": [{"descripcion": "nombre producto", '
                    '"cantidad": 1, "precio_unitario": 10.50, "subtotal": 10.50}], '
                    '"total": 100.00, "notas": "cualquier observación relevante"}'
                )}
            ]
        })
    elif texto_ticket:
        messages.append({
            'role': 'user',
            'content': (
                f'Analiza este texto de ticket de proveedor y extrae la información en JSON. '
                f'Responde SOLO con JSON válido sin markdown:\n\n{texto_ticket}\n\n'
                f'Estructura: {{"proveedor": "", "fecha": "YYYY-MM-DD", "folio": "", '
                f'"items": [{{"descripcion": "", "cantidad": 1, "precio_unitario": 0, "subtotal": 0}}], '
                f'"total": 0, "notas": ""}}'
            )
        })
    else:
        return {'error': 'Se requiere imagen o texto del ticket'}

    import requests as req_lib

    modelo = getattr(__import__('django.conf', fromlist=['settings']).settings,
                     'ANTHROPIC_MODEL', 'claude-sonnet-4-6')
    payload = {'model': modelo, 'max_tokens': 1000, 'messages': messages}
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
    }

    ultimo_error = None
    for intento in range(1, 3):  # 2 intentos
        try:
            resp = req_lib.post(
                'https://api.anthropic.com/v1/messages',
                json=payload, headers=headers, timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            texto = result['content'][0]['text'].strip()
            if texto.startswith('```'):
                texto = texto.split('```')[1]
                if texto.startswith('json'):
                    texto = texto[4:]
            return json.loads(texto.strip())
        except Exception as e:
            ultimo_error = e
            logger.warning(f'analizar_ticket_ia intento {intento} falló: {e}')

    logger.error(f'Error analizando ticket tras 2 intentos: {ultimo_error}')
    return {'error': str(ultimo_error)}


# ── COMPARACIÓN DE PRECIOS PROVEEDORES ────────────────────

def comparar_precios_producto(producto):
    """
    Retorna comparativa de precios de todos los proveedores para un producto.
    """
    from .models import PrecioHistoricoProveedor
    from django.db.models import Min, Max, Avg

    historico = PrecioHistoricoProveedor.objects.filter(
        producto=producto
    ).select_related('proveedor').order_by('proveedor', '-fecha')

    proveedores = {}
    for h in historico:
        prov_id = h.proveedor.id
        if prov_id not in proveedores:
            proveedores[prov_id] = {
                'proveedor': h.proveedor.nombre,
                'ultimo_precio': h.costo,
                'ultima_fecha': h.fecha,
                'historial': [],
            }
        proveedores[prov_id]['historial'].append({
            'precio': float(h.costo),
            'fecha': h.fecha.strftime('%d/%m/%Y'),
        })

    return list(proveedores.values())


def reporte_ganancias_sucursal(sucursal, fecha_inicio, fecha_fin):
    """Calcula ventas, costos y ganancia neta de una sucursal en un rango de fechas."""
    from django.db.models import Sum
    from .models import Venta

    ventas = Venta.objects.filter(
        sucursal=sucursal,
        creado__date__gte=fecha_inicio,
        creado__date__lte=fecha_fin,
        estado__in=['pagada', 'credito'],
    )

    totals = ventas.aggregate(
        total_ventas=Sum('total'),
        total_costos=Sum('costo_total'),
        total_descuentos=Sum('descuento'),
    )

    total_ventas    = totals['total_ventas']    or Decimal('0')
    total_costos    = totals['total_costos']    or Decimal('0')
    total_descuentos = totals['total_descuentos'] or Decimal('0')
    ganancia_neta   = total_ventas - total_costos - total_descuentos
    margen          = (ganancia_neta / total_ventas * 100) if total_ventas > 0 else Decimal('0')
    config          = ConfigPOS.get()
    reinversion     = ganancia_neta * (config.pct_reinversion / Decimal('100'))

    return {
        'sucursal':       sucursal.nombre,
        'fecha_inicio':   fecha_inicio,
        'fecha_fin':      fecha_fin,
        'num_ventas':     ventas.count(),
        'total_ventas':   total_ventas,
        'total_costos':   total_costos,
        'total_descuentos': total_descuentos,
        'ganancia_neta':  ganancia_neta,
        'margen_pct':     round(margen, 2),
        'reinversion_sugerida': reinversion,
    }
