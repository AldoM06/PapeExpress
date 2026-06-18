import json
import logging
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone

from .models import (
    Sucursal, ProductoPOS, PrecioPorSucursal, Inventario,
    Venta, DetalleVenta, Abono, Anticipo,
    Proveedor, CompraProveedor, PrecioHistoricoProveedor,
    CategoriaPOS,
)
from .services import (
    crear_venta, registrar_compra, analizar_ticket_ia,
    comparar_precios_producto, reporte_ganancias_sucursal,
)

logger = logging.getLogger(__name__)


def _get_sucursal(request):
    """Obtiene la sucursal activa del usuario."""
    try:
        us = request.user.sucursales_pos.filter(activo=True).select_related('sucursal').first()
        return us.sucursal if us else None
    except Exception:
        return None


def _es_admin(user):
    return user.is_superuser or getattr(user, 'rol', '') == 'admin'


# ── POS PRINCIPAL ──────────────────────────────────────────
@login_required
def pos_view(request):
    sucursal = _get_sucursal(request)
    if not sucursal and not _es_admin(request.user):
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('home')

    categorias = CategoriaPOS.objects.all()
    return render(request, 'pos/pos.html', {
        'sucursal':   sucursal,
        'categorias': categorias,
    })


@login_required
@require_GET
def productos_api(request):
    """API para buscar productos en el POS."""
    sucursal = _get_sucursal(request)
    q        = request.GET.get('q', '')
    cat_id   = request.GET.get('cat', '')

    prods = ProductoPOS.objects.filter(activo=True)
    if q:
        prods = prods.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
    if cat_id:
        prods = prods.filter(categoria_id=cat_id)

    resultado = []
    for p in prods[:50]:
        precio_obj = None
        if sucursal:
            precio_obj = PrecioPorSucursal.objects.filter(producto=p, sucursal=sucursal, activo=True).first()
        inv = Inventario.objects.filter(producto=p, sucursal=sucursal).first() if sucursal else None

        resultado.append({
            'id':       p.id,
            'codigo':   p.codigo,
            'nombre':   p.nombre,
            'unidad':   p.unidad,
            'imagen':   p.imagen.url if p.imagen else None,
            'precio_1': float(precio_obj.precio_1) if precio_obj else 0,
            'precio_2': float(precio_obj.precio_2) if precio_obj and precio_obj.precio_2 else None,
            'precio_3': float(precio_obj.precio_3) if precio_obj and precio_obj.precio_3 else None,
            'en_oferta': precio_obj.en_oferta if precio_obj else False,
            'precio_oferta': float(precio_obj.precio_oferta) if precio_obj and precio_obj.precio_oferta else None,
            'stock':    float(inv.stock_actual) if inv else 0,
            'costo':    float(inv.costo_promedio) if inv else 0,
        })
    return JsonResponse({'productos': resultado})


@login_required
@require_POST
def procesar_venta(request):
    """Procesa una venta desde el POS."""
    sucursal = _get_sucursal(request)
    if not sucursal:
        return JsonResponse({'error': 'Sin sucursal asignada'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    items_raw  = data.get('items', [])
    forma_pago = data.get('forma_pago', 'efectivo')
    total_pagado = data.get('total_pagado')
    notas = data.get('notas', '')

    if not items_raw:
        return JsonResponse({'error': 'Sin productos en la venta'}, status=400)

    items = []
    for it in items_raw:
        try:
            prod = ProductoPOS.objects.get(pk=it['producto_id'])
        except ProductoPOS.DoesNotExist:
            return JsonResponse({'error': f'Producto {it["producto_id"]} no encontrado'}, status=400)

        inv = Inventario.objects.filter(producto=prod, sucursal=sucursal).first()
        items.append({
            'producto':  prod,
            'cantidad':  it['cantidad'],
            'precio':    it['precio'],
            'costo':     float(inv.costo_promedio) if inv else 0,
            'nivel':     it.get('nivel', 1),
            'descuento': it.get('descuento', 0),
        })

    try:
        venta = crear_venta(
            sucursal=sucursal,
            cajero=request.user,
            items=items,
            forma_pago=forma_pago,
            total_pagado=total_pagado,
            notas=notas,
        )
        return JsonResponse({
            'ok':    True,
            'folio': venta.folio,
            'total': float(venta.total),
            'saldo': float(venta.saldo_pendiente),
        })
    except Exception as e:
        logger.error(f'Error procesando venta: {e}', exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# ── ABONOS ────────────────────────────────────────────────
@login_required
def ventas_credito(request):
    sucursal = _get_sucursal(request)
    ventas = Venta.objects.filter(
        sucursal=sucursal, estado='credito', saldo_pendiente__gt=0
    ).order_by('-creado') if sucursal else Venta.objects.none()
    return render(request, 'pos/ventas_credito.html', {'ventas': ventas, 'sucursal': sucursal})


@login_required
@require_POST
def agregar_abono(request, venta_pk):
    venta = get_object_or_404(Venta, pk=venta_pk)
    monto = Decimal(request.POST.get('monto', '0'))
    forma = request.POST.get('forma_pago', 'efectivo')
    notas = request.POST.get('notas', '')
    if monto > 0:
        Abono.objects.create(venta=venta, monto=monto, forma_pago=forma,
                              usuario=request.user, notas=notas)
        messages.success(request, f'Abono de ${monto} registrado. Saldo: ${venta.saldo_pendiente}')
    return redirect('ventas_credito')


# ── ANTICIPOS ─────────────────────────────────────────────
@login_required
def anticipos_view(request):
    sucursal = _get_sucursal(request)
    if request.method == 'POST':
        Anticipo.objects.create(
            sucursal=sucursal,
            cliente_nombre=request.POST.get('cliente_nombre'),
            cliente_tel=request.POST.get('cliente_tel', ''),
            descripcion=request.POST.get('descripcion'),
            total_pedido=Decimal(request.POST.get('total_pedido', '0')),
            anticipo_pagado=Decimal(request.POST.get('anticipo_pagado', '0')),
            fecha_prometida=request.POST.get('fecha_prometida') or None,
            usuario=request.user,
        )
        messages.success(request, 'Anticipo registrado correctamente.')
        return redirect('anticipos')

    anticipos = Anticipo.objects.filter(
        sucursal=sucursal, entregado=False
    ).order_by('-creado') if sucursal else Anticipo.objects.none()
    return render(request, 'pos/anticipos.html', {'anticipos': anticipos, 'sucursal': sucursal})


# ── INVENTARIO ────────────────────────────────────────────
@login_required
def inventario_view(request):
    sucursal = _get_sucursal(request)
    if _es_admin(request.user):
        sucursal_id = request.GET.get('sucursal')
        if sucursal_id:
            sucursal = get_object_or_404(Sucursal, pk=sucursal_id)

    q = request.GET.get('q', '')
    solo_criticos = request.GET.get('criticos', '')

    inventarios = Inventario.objects.filter(
        sucursal=sucursal
    ).select_related('producto', 'producto__categoria') if sucursal else Inventario.objects.none()

    if q:
        inventarios = inventarios.filter(
            Q(producto__nombre__icontains=q) | Q(producto__codigo__icontains=q)
        )
    if solo_criticos:
        inventarios = [i for i in inventarios if i.bajo_minimo]

    sucursales = Sucursal.objects.filter(activa=True) if _es_admin(request.user) else []

    return render(request, 'pos/inventario.html', {
        'inventarios': inventarios,
        'sucursal':    sucursal,
        'sucursales':  sucursales,
        'q': q,
        'solo_criticos': solo_criticos,
    })


# ── COMPRAS / PROVEEDORES ─────────────────────────────────
@login_required
def compras_view(request):
    sucursal  = _get_sucursal(request)
    compras   = CompraProveedor.objects.filter(sucursal=sucursal).select_related('proveedor') \
        if sucursal else CompraProveedor.objects.select_related('proveedor', 'sucursal').all()
    proveedores = Proveedor.objects.filter(activo=True)
    return render(request, 'pos/compras.html', {
        'compras': compras[:50],
        'proveedores': proveedores,
        'sucursal': sucursal,
    })


@login_required
@require_POST
def analizar_ticket(request):
    """Analiza el ticket subido usando Claude IA."""
    compra_id = request.POST.get('compra_id')
    compra = get_object_or_404(CompraProveedor, pk=compra_id)

    imagen_path = compra.ticket_imagen.path if compra.ticket_imagen else None
    resultado = analizar_ticket_ia(imagen_path=imagen_path)

    if 'error' not in resultado:
        compra.analisis_ocr = json.dumps(resultado, ensure_ascii=False, indent=2)
        if not compra.folio and resultado.get('folio'):
            compra.folio = resultado['folio']
        compra.save()

    return JsonResponse(resultado)


# ── COMPARAR PRECIOS ──────────────────────────────────────
@login_required
def comparar_precios(request):
    producto_id = request.GET.get('producto')
    producto    = get_object_or_404(ProductoPOS, pk=producto_id) if producto_id else None
    comparativa = comparar_precios_producto(producto) if producto else []
    productos   = ProductoPOS.objects.filter(activo=True).order_by('nombre')
    return render(request, 'pos/comparar_precios.html', {
        'productos':   productos,
        'producto':    producto,
        'comparativa': comparativa,
    })


# ── DASHBOARD ADMIN ───────────────────────────────────────
@login_required
def dashboard_admin_pos(request):
    if not _es_admin(request.user):
        return redirect('pos')

    hoy        = date.today()
    inicio_mes = hoy.replace(day=1)

    sucursales = Sucursal.objects.filter(activa=True).select_related('cliente')
    reportes   = []
    for suc in sucursales:
        rep = reporte_ganancias_sucursal(suc, inicio_mes, hoy)
        # Ventas de hoy
        ventas_hoy = Venta.objects.filter(
            sucursal=suc, creado__date=hoy, estado__in=['pagada', 'credito']
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        rep['ventas_hoy'] = ventas_hoy
        reportes.append(rep)

    total_mes     = sum(r['total_ventas']   for r in reportes)
    ganancia_mes  = sum(r['ganancia_neta']  for r in reportes)
    reinversion   = ganancia_mes * Decimal('0.40')

    # Productos críticos
    criticos = [i for i in Inventario.objects.select_related('producto', 'sucursal').all()
                if i.bajo_minimo]

    return render(request, 'pos/dashboard_admin.html', {
        'reportes':    reportes,
        'total_mes':   total_mes,
        'ganancia_mes': ganancia_mes,
        'reinversion': reinversion,
        'criticos':    criticos[:20],
        'hoy':         hoy,
        'inicio_mes':  inicio_mes,
    })


# ── API BARRIDO MANUAL ────────────────────────────────────
@login_required
def barrido_manual(request):
    if not _es_admin(request.user):
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    from .tasks import barrido_inventario_critico
    barrido_inventario_critico()
    messages.success(request, 'Barrido de inventario ejecutado. Revisa Telegram.')
    return redirect('dashboard_admin_pos')
