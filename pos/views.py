import json
import logging
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.db.models import F, Sum, Q
from django.utils import timezone

from .models import (
    Sucursal, ProductoPOS, PrecioPorSucursal, Inventario, MovimientoInventario,
    Venta, DetalleVenta, Abono, Anticipo,
    Proveedor, CompraProveedor, PrecioHistoricoProveedor,
    CategoriaPOS, UsuarioSucursal, ConfigPOS, GastoFijo, SolicitudCancelacion,
    TraspasoSucursal, DetalleTraspaso, GastoOperativo,
    CierreCaja, RetiroEfectivo, TransaccionServicio,
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
    return user.is_superuser or getattr(user, 'rol', '') in ('admin', 'operador')


# ── POS PRINCIPAL ──────────────────────────────────────────
@login_required
def pos_view(request):
    sucursal = _get_sucursal(request)
    if not sucursal and not _es_admin(request.user):
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('home')

    # Cajeros y vendedores deben abrir caja antes de vender
    if sucursal and not _es_admin(request.user):
        caja_hoy = CierreCaja.objects.filter(sucursal=sucursal, fecha=date.today()).first()
        if not caja_hoy:
            messages.warning(request, 'Debes abrir la caja antes de iniciar ventas.')
            return redirect('apertura_caja')

    categorias = CategoriaPOS.objects.all()
    return render(request, 'pos/pos.html', {
        'sucursal':    sucursal,
        'categorias':  categorias,
        'suc_tel':     sucursal.telefono  if sucursal else '',
        'suc_dir':     sucursal.direccion if sucursal else '',
        'suc_wa':      sucursal.whatsapp  if sucursal else '',
        'suc_logo':    sucursal.logo.url  if sucursal and sucursal.logo else '',
    })


@login_required
@require_GET
def productos_api(request):
    """API para buscar productos en el POS."""
    sucursal = _get_sucursal(request)
    q        = request.GET.get('q', '')
    cat_id   = request.GET.get('cat', '')
    tab      = request.GET.get('tab', '')   # favoritos | ofertas | '' (todos)

    prods = ProductoPOS.objects.filter(activo=True).select_related('categoria')

    # Solo mostrar productos que tienen precio e inventario en ESTA sucursal
    if sucursal:
        prods_con_precio = PrecioPorSucursal.objects.filter(
            sucursal=sucursal, activo=True
        ).values_list('producto_id', flat=True)
        prods_con_stock = Inventario.objects.filter(
            sucursal=sucursal, stock_actual__gt=0
        ).values_list('producto_id', flat=True)
        # Mostrar si tiene precio en esta sucursal Y (tiene stock O es favorito)
        prods = prods.filter(
            Q(pk__in=prods_con_precio) & (Q(pk__in=prods_con_stock) | Q(favorito_pos=True))
        )

    if tab == 'favoritos':
        prods = prods.filter(favorito_pos=True)
    elif tab == 'ofertas':
        if sucursal:
            oferta_ids = PrecioPorSucursal.objects.filter(
                sucursal=sucursal, en_oferta=True, activo=True
            ).values_list('producto_id', flat=True)
        else:
            oferta_ids = PrecioPorSucursal.objects.filter(
                en_oferta=True, activo=True
            ).values_list('producto_id', flat=True)
        prods = prods.filter(pk__in=oferta_ids)
    if q:
        prods = prods.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
    if cat_id:
        prods = prods.filter(categoria_id=cat_id)

    prods = prods[:50]

    # Prefetch precios e inventarios de la sucursal en 2 queries en lugar de N*2
    if sucursal:
        ids = [p.id for p in prods]
        precios_map = {
            pp.producto_id: pp
            for pp in PrecioPorSucursal.objects.filter(
                producto_id__in=ids, sucursal=sucursal, activo=True
            )
        }
        inv_map = {
            inv.producto_id: inv
            for inv in Inventario.objects.filter(
                producto_id__in=ids, sucursal=sucursal
            )
        }
    else:
        precios_map, inv_map = {}, {}

    resultado = []
    for p in prods:
        precio_obj = precios_map.get(p.id)
        inv        = inv_map.get(p.id)
        resultado.append({
            'id':            p.id,
            'codigo':        p.codigo,
            'nombre':        p.nombre,
            'unidad':        p.unidad,
            'imagen':        p.imagen.url if p.imagen else None,
            'favorito_pos':  p.favorito_pos,
            'precio_1':      float(precio_obj.precio_1)      if precio_obj else 0,
            'precio_2':      float(precio_obj.precio_2)      if precio_obj and precio_obj.precio_2 else None,
            'precio_3':      float(precio_obj.precio_3)      if precio_obj and precio_obj.precio_3 else None,
            'en_oferta':     precio_obj.en_oferta            if precio_obj else False,
            'precio_oferta': float(precio_obj.precio_oferta) if precio_obj and precio_obj.precio_oferta else None,
            'stock':         float(inv.stock_actual)         if inv else 0,
            'costo':         float(inv.costo_promedio)       if inv else 0,
        })
    return JsonResponse({'productos': resultado})


@login_required
@require_POST
def procesar_venta(request):
    """Procesa una venta desde el POS."""
    sucursal = _get_sucursal(request)
    if not sucursal:
        return JsonResponse({'error': 'Sin sucursal asignada'}, status=400)

    # Verificar que existe caja registrada hoy (exentos: admins)
    if not _es_admin(request.user):
        if not CierreCaja.objects.filter(sucursal=sucursal, fecha=date.today()).exists():
            return JsonResponse({'error': 'No hay caja abierta hoy. Abre la caja antes de vender.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    items_raw      = data.get('items', [])
    forma_pago     = data.get('forma_pago', 'efectivo')
    total_pagado   = data.get('total_pagado')
    monto_recibido = Decimal(str(data.get('monto_recibido', 0) or 0))
    notas          = data.get('notas', '')

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
        # Guardar monto recibido y cambio para efectivo
        if forma_pago == 'efectivo' and monto_recibido > 0:
            venta.monto_recibido = monto_recibido
            venta.cambio         = max(monto_recibido - venta.total, Decimal('0'))
            venta.save(update_fields=['monto_recibido', 'cambio'])

        return JsonResponse({
            'ok':            True,
            'folio':         venta.folio,
            'total':         float(venta.total),
            'saldo':         float(venta.saldo_pendiente),
            'monto_recibido': float(venta.monto_recibido),
            'cambio':        float(venta.cambio),
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
        inventarios = inventarios.filter(
            stock_actual__lte=F('stock_minimo'), stock_minimo__gt=0
        )

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

    sucursales = Sucursal.objects.filter(activa=True).select_related('cliente').prefetch_related('gastos_fijos')
    reportes   = []
    for suc in sucursales:
        rep = reporte_ganancias_sucursal(suc, inicio_mes, hoy)
        ventas_hoy = Venta.objects.filter(
            sucursal=suc, creado__date=hoy, estado__in=['pagada', 'credito']
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        rep['ventas_hoy'] = ventas_hoy

        # Gastos fijos activos de la sucursal
        gastos = list(suc.gastos_fijos.filter(activo=True))
        total_gastos = sum(g.monto for g in gastos)
        rep['gastos_fijos']   = gastos
        rep['total_gastos']   = total_gastos
        rep['utilidad_real']  = rep['ganancia_neta'] - total_gastos
        rep['margen_real_pct'] = (
            round(rep['utilidad_real'] / rep['total_ventas'] * 100, 1)
            if rep['total_ventas'] else Decimal('0')
        )
        reportes.append(rep)

    total_mes       = sum(r['total_ventas']   for r in reportes)
    ganancia_mes    = sum(r['ganancia_neta']  for r in reportes)
    total_gastos_gl = sum(r['total_gastos']   for r in reportes)
    utilidad_real   = ganancia_mes - total_gastos_gl
    config          = ConfigPOS.get()
    reinversion     = utilidad_real * (config.pct_reinversion / Decimal('100'))
    pct_utilidad_gl = round(utilidad_real / total_mes * 100, 1) if total_mes else Decimal('0')

    # Productos críticos — filtro en SQL, no en Python
    criticos = Inventario.objects.select_related('producto', 'sucursal').filter(
        stock_actual__lte=F('stock_minimo'), stock_minimo__gt=0,
        sucursal__activa=True,
    ).order_by('sucursal__nombre', 'producto__nombre')

    inicio_semana = hoy - timedelta(days=hoy.weekday())

    # Top global (todas las sucursales)
    top_mes = (
        DetalleVenta.objects.filter(venta__creado__date__gte=inicio_mes, venta__estado__in=['pagada','credito'])
        .values('producto__id', 'producto__nombre')
        .annotate(total_uds=Sum('cantidad'), total_pesos=Sum('subtotal'))
        .order_by('-total_uds')[:10]
    )
    top_semana = (
        DetalleVenta.objects.filter(venta__creado__date__gte=inicio_semana, venta__estado__in=['pagada','credito'])
        .values('producto__id', 'producto__nombre')
        .annotate(total_uds=Sum('cantidad'), total_pesos=Sum('subtotal'))
        .order_by('-total_uds')[:10]
    )

    # Top por sucursal (día y semana) para anticipar compras
    top_por_sucursal = []
    for suc in sucursales:
        dia = (
            DetalleVenta.objects.filter(
                venta__sucursal=suc, venta__creado__date=hoy,
                venta__estado__in=['pagada','credito']
            ).values('producto__nombre')
            .annotate(uds=Sum('cantidad'), pesos=Sum('subtotal'))
            .order_by('-uds')[:8]
        )
        semana = (
            DetalleVenta.objects.filter(
                venta__sucursal=suc, venta__creado__date__gte=inicio_semana,
                venta__estado__in=['pagada','credito']
            ).values('producto__nombre')
            .annotate(uds=Sum('cantidad'), pesos=Sum('subtotal'))
            .order_by('-uds')[:8]
        )
        # Stock actual de los top productos de la semana para alertas
        productos_semana_ids = (
            DetalleVenta.objects.filter(
                venta__sucursal=suc, venta__creado__date__gte=inicio_semana,
                venta__estado__in=['pagada','credito']
            ).values('producto__id', 'producto__nombre')
            .annotate(uds=Sum('cantidad'))
            .order_by('-uds')[:8]
        )
        stocks = {}
        if productos_semana_ids:
            pids = [p['producto__id'] for p in productos_semana_ids]
            for inv in Inventario.objects.filter(sucursal=suc, producto_id__in=pids).select_related('producto'):
                stocks[inv.producto_id] = inv.stock_actual

        semana_con_stock = []
        for p in productos_semana_ids:
            stock = stocks.get(p['producto__id'], 0)
            semana_con_stock.append({
                'nombre': p['producto__nombre'],
                'uds': p['uds'],
                'stock': stock,
                'alerta': stock < p['uds'],  # vendió más en la semana que lo que tiene ahora
            })

        top_por_sucursal.append({
            'sucursal': suc,
            'dia':      list(dia),
            'semana':   semana_con_stock,
        })

    # Cierres de caja de hoy por sucursal
    cierres_hoy = list(CierreCaja.objects.filter(fecha=hoy).select_related('sucursal', 'usuario_apertura', 'usuario_cierre').order_by('sucursal__nombre'))
    suc_con_caja = {c.sucursal_id for c in cierres_hoy}
    sucursales_sin_caja = [s for s in sucursales if s.pk not in suc_con_caja]

    return render(request, 'pos/dashboard_admin.html', {
        'reportes':     reportes,
        'total_mes':    total_mes,
        'ganancia_mes': ganancia_mes,
        'reinversion':  reinversion,
        'criticos':     criticos[:20],
        'hoy':          hoy,
        'inicio_mes':   inicio_mes,
        'top_mes':          top_mes,
        'top_semana':       top_semana,
        'top_por_sucursal': top_por_sucursal,
        'pct_reinversion':  config.pct_reinversion,
        'total_gastos_gl':  total_gastos_gl,
        'utilidad_real':    utilidad_real,
        'pct_utilidad_gl':  pct_utilidad_gl,
        'cierres_hoy':         cierres_hoy,
        'sucursales':          sucursales,
        'sucursales_sin_caja': sucursales_sin_caja,
    })


# ── AGREGAR PRODUCTO ─────────────────────────────────────
@login_required
def crear_producto(request):
    if not _es_admin(request.user):
        messages.error(request, 'No tienes permisos para agregar productos.')
        return redirect('pos')

    categorias = CategoriaPOS.objects.all().order_by('nombre')

    if request.method == 'POST':
        nombre     = request.POST.get('nombre', '').strip()
        codigo     = request.POST.get('codigo', '').strip()
        categoria_id = request.POST.get('categoria') or None
        descripcion = request.POST.get('descripcion', '').strip()
        unidad     = request.POST.get('unidad', 'pieza').strip()
        peso_str   = request.POST.get('peso', '0').strip() or '0'
        imagen     = request.FILES.get('imagen')

        if not nombre or not codigo:
            messages.error(request, 'El nombre y el código son obligatorios.')
            return render(request, 'pos/crear_producto.html', {'categorias': categorias, 'post': request.POST})

        if ProductoPOS.objects.filter(codigo=codigo).exists():
            messages.error(request, f'Ya existe un producto con el código "{codigo}".')
            unidades = ['pieza', 'caja', 'paquete', 'kg', 'litro', 'metro', 'par', 'docena', 'resma']
            return render(request, 'pos/crear_producto.html', {'categorias': categorias, 'post': request.POST, 'unidades': unidades})

        try:
            peso = Decimal(peso_str)
        except Exception:
            peso = Decimal('0')

        producto = ProductoPOS.objects.create(
            nombre=nombre,
            codigo=codigo,
            categoria_id=categoria_id,
            descripcion=descripcion,
            unidad=unidad,
            peso=peso,
            imagen=imagen,
        )
        messages.success(request, f'Producto "{producto.nombre}" creado correctamente.')
        return redirect('pos_productos_lista')

    unidades = ['pieza', 'caja', 'paquete', 'kg', 'litro', 'metro', 'par', 'docena', 'resma']
    return render(request, 'pos/crear_producto.html', {'categorias': categorias, 'post': {}, 'unidades': unidades})


@login_required
def productos_lista(request):
    """Lista de todos los productos POS con opción de editar."""
    if not _es_admin(request.user):
        return redirect('pos')
    q = request.GET.get('q', '')
    productos = ProductoPOS.objects.select_related('categoria').filter(activo=True)
    if q:
        productos = productos.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
    return render(request, 'pos/productos_lista.html', {
        'productos': productos.order_by('nombre'),
        'q': q,
    })


@login_required
def margenes_productos(request):
    if not _es_admin(request.user):
        return redirect('pos')

    sucursales = Sucursal.objects.filter(activa=True).order_by('nombre')
    suc_id = request.GET.get('sucursal')
    sucursal = get_object_or_404(Sucursal, pk=suc_id) if suc_id else sucursales.first()

    # Productos activos con su precio y costo para la sucursal seleccionada
    productos = ProductoPOS.objects.filter(activo=True).order_by('categoria__nombre', 'nombre')

    precios_map = {}
    if sucursal:
        for pp in PrecioPorSucursal.objects.filter(sucursal=sucursal).select_related('producto'):
            precios_map[pp.producto_id] = pp

    costos_map = {}
    if sucursal:
        for inv in Inventario.objects.filter(sucursal=sucursal).select_related('producto'):
            costos_map[inv.producto_id] = inv

    filas = []
    for prod in productos:
        pp  = precios_map.get(prod.id)
        inv = costos_map.get(prod.id)
        costo = float(inv.costo_promedio) if inv else 0

        def margen(precio):
            if precio and precio > 0 and costo > 0:
                return round((float(precio) - costo) / float(precio) * 100, 1)
            return None

        filas.append({
            'producto':   prod,
            'pp':         pp,
            'pp_id':      pp.id if pp else None,
            'costo':      costo,
            'stock':      inv.stock_actual if inv else 0,
            'precio_1':   float(pp.precio_1) if pp else 0,
            'precio_2':   float(pp.precio_2) if pp and pp.precio_2 else 0,
            'precio_3':   float(pp.precio_3) if pp and pp.precio_3 else 0,
            'margen_1':   margen(pp.precio_1) if pp else None,
            'margen_2':   margen(pp.precio_2) if pp and pp.precio_2 else None,
            'margen_3':   margen(pp.precio_3) if pp and pp.precio_3 else None,
            'en_oferta':       pp.en_oferta if pp else False,
            'precio_oferta':   float(pp.precio_oferta)   if pp and pp.precio_oferta   else 0,
            'precio_traspaso': float(pp.precio_traspaso) if pp and pp.precio_traspaso else 0,
        })

    return render(request, 'pos/margenes_productos.html', {
        'filas':      filas,
        'sucursal':   sucursal,
        'sucursales': sucursales,
    })


@login_required
def comparar_precios_sucursales(request):
    """Tabla de discrepancias P1/P2 entre sucursales con opción de igualar."""
    if not _es_admin(request.user):
        return redirect('pos')

    sucursales = list(Sucursal.objects.filter(activa=True).order_by('nombre'))
    productos  = ProductoPOS.objects.filter(activo=True).order_by('categoria__nombre', 'nombre').select_related('categoria')

    # Cargar todos los precios de una vez: {(prod_id, suc_id): pp}
    precios_qs = PrecioPorSucursal.objects.filter(sucursal__in=sucursales)
    precios_map = {}
    for pp in precios_qs:
        precios_map[(pp.producto_id, pp.sucursal_id)] = pp

    filas = []
    for prod in productos:
        precios_por_suc = []
        p1_vals, p2_vals = [], []
        for suc in sucursales:
            pp = precios_map.get((prod.id, suc.id))
            p1 = float(pp.precio_1) if pp and pp.precio_1 else None
            p2 = float(pp.precio_2) if pp and pp.precio_2 else None
            precios_por_suc.append({
                'sucursal': suc,
                'pp_id':    pp.id if pp else None,
                'p1':       p1,
                'p2':       p2,
            })
            if p1 is not None:
                p1_vals.append(p1)
            if p2 is not None:
                p2_vals.append(p2)

        diff_p1 = len(set(p1_vals)) > 1
        diff_p2 = len(set(p2_vals)) > 1
        tiene_diff = diff_p1 or diff_p2

        filas.append({
            'producto':    prod,
            'sucursales':  precios_por_suc,
            'diff_p1':     diff_p1,
            'diff_p2':     diff_p2,
            'tiene_diff':  tiene_diff,
        })

    solo_diff = request.GET.get('solo_diff') == '1'
    if solo_diff:
        filas = [f for f in filas if f['tiene_diff']]

    return render(request, 'pos/comparar_precios_sucursales.html', {
        'filas':      filas,
        'sucursales': sucursales,
        'solo_diff':  solo_diff,
    })


@login_required
@require_POST
def igualar_precio_sucursales(request, prod_id):
    """Copia P1 y/o P2 de una sucursal origen a todas las demás."""
    if not _es_admin(request.user):
        return JsonResponse({'ok': False}, status=403)
    try:
        data     = json.loads(request.body)
        campo    = data.get('campo')        # 'precio_1' | 'precio_2' | 'ambos'
        suc_orig = int(data.get('suc_id'))  # id de la sucursal origen

        if campo not in ('precio_1', 'precio_2', 'ambos'):
            return JsonResponse({'ok': False, 'error': 'campo inválido'})

        producto   = get_object_or_404(ProductoPOS, pk=prod_id)
        pp_origen  = get_object_or_404(PrecioPorSucursal, producto=producto, sucursal_id=suc_orig)

        campos_a_copiar = ['precio_1', 'precio_2'] if campo == 'ambos' else [campo]
        sucursales = Sucursal.objects.filter(activa=True).exclude(pk=suc_orig)

        actualizados = []
        for suc in sucursales:
            pp, _ = PrecioPorSucursal.objects.get_or_create(
                producto=producto, sucursal=suc,
                defaults={'precio_1': pp_origen.precio_1},
            )
            for c in campos_a_copiar:
                setattr(pp, c, getattr(pp_origen, c))
            pp.save(update_fields=campos_a_copiar)
            actualizados.append(suc.nombre)

        return JsonResponse({'ok': True, 'actualizadas': actualizados})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


# ── Traspasos entre sucursales ────────────────────────────

def _siguiente_folio_traspaso():
    from datetime import date
    prefijo = f"TRP-{date.today().strftime('%y%m')}-"
    ultimo  = TraspasoSucursal.objects.filter(folio__startswith=prefijo).order_by('-folio').first()
    num     = int(ultimo.folio.split('-')[-1]) + 1 if ultimo else 1
    return f"{prefijo}{num:03d}"


@login_required
def traspasos_lista(request):
    if not (_es_admin(request.user) or request.user.sucursales_pos.exists()):
        return redirect('pos')

    sucursal_user = _get_sucursal(request)
    qs = TraspasoSucursal.objects.select_related(
        'sucursal_origen', 'sucursal_destino', 'solicitado_por'
    ).prefetch_related('detalles__producto')

    # Admin ve todos; gerente/cajero solo los de su sucursal
    if not _es_admin(request.user) and sucursal_user:
        qs = qs.filter(
            Q(sucursal_origen=sucursal_user) | Q(sucursal_destino=sucursal_user)
        )

    estado = request.GET.get('estado', '')
    if estado:
        qs = qs.filter(estado=estado)

    return render(request, 'pos/traspasos_lista.html', {
        'traspasos':    qs[:100],
        'estado_sel':   estado,
        'sucursal_user': sucursal_user,
    })


@login_required
def traspaso_nuevo(request):
    if not (_es_admin(request.user) or request.user.sucursales_pos.exists()):
        return redirect('pos')

    sucursal_user = _get_sucursal(request)
    sucursales    = Sucursal.objects.filter(activa=True).order_by('nombre')

    if request.method == 'POST':
        orig_id    = request.POST.get('sucursal_origen')
        dest_id    = request.POST.get('sucursal_destino')
        notas      = request.POST.get('notas', '')
        forma_pago = request.POST.get('forma_pago', 'efectivo')
        prod_ids   = request.POST.getlist('producto_id')
        cantids    = request.POST.getlist('cantidad')

        errores = []
        if orig_id == dest_id:
            errores.append('Origen y destino no pueden ser la misma sucursal.')
        if not prod_ids:
            errores.append('Agrega al menos un producto.')

        if not errores:
            with transaction.atomic():
                traspaso = TraspasoSucursal.objects.create(
                    folio               = _siguiente_folio_traspaso(),
                    sucursal_origen_id  = orig_id,
                    sucursal_destino_id = dest_id,
                    solicitado_por      = request.user,
                    notas               = notas,
                    forma_pago          = forma_pago,
                )
                total = Decimal('0')
                for pid, cant in zip(prod_ids, cantids):
                    try:
                        cant_dec = Decimal(cant)
                        if cant_dec <= 0:
                            continue
                        prod = ProductoPOS.objects.get(pk=pid)
                        inv  = Inventario.objects.filter(producto=prod, sucursal_id=orig_id).first()
                        pp   = PrecioPorSucursal.objects.filter(producto=prod, sucursal_id=orig_id).first()
                        precio_t = pp.precio_traspaso if pp and pp.precio_traspaso else (
                                   pp.precio_2 if pp and pp.precio_2 else
                                   pp.precio_1 if pp else Decimal('0'))
                        subtotal = cant_dec * precio_t
                        total   += subtotal
                        DetalleTraspaso.objects.create(
                            traspaso             = traspaso,
                            producto             = prod,
                            cantidad             = cant_dec,
                            costo_unitario       = inv.costo_promedio if inv else Decimal('0'),
                            precio_traspaso_unit = precio_t,
                            subtotal_traspaso    = subtotal,
                        )
                    except (ProductoPOS.DoesNotExist, Exception):
                        pass
                traspaso.total = total
                traspaso.save(update_fields=['total'])

            from produccion.telegram import notificar_traspaso
            notificar_traspaso(traspaso, 'solicitado')
            messages.success(request, f'Traspaso {traspaso.folio} solicitado. Total: ${total}.')
            return redirect('traspasos_lista')

        return render(request, 'pos/traspaso_nuevo.html', {
            'sucursales':    sucursales,
            'sucursal_user': sucursal_user,
            'errores':       errores,
            'post':          request.POST,
        })

    return render(request, 'pos/traspaso_nuevo.html', {
        'sucursales':    sucursales,
        'sucursal_user': sucursal_user,
    })


@login_required
def traspaso_aprobar(request, pk):
    """Origen aprueba: descuenta inventario y registra venta interna."""
    traspaso = get_object_or_404(TraspasoSucursal, pk=pk)
    sucursal_user = _get_sucursal(request)

    puede = _es_admin(request.user) or (
        sucursal_user and sucursal_user == traspaso.sucursal_origen
    )
    if not puede:
        messages.error(request, 'Sin permiso para aprobar este traspaso.')
        return redirect('traspasos_lista')

    if traspaso.estado != 'solicitado':
        messages.error(request, f'El traspaso está en estado "{traspaso.get_estado_display()}", no se puede aprobar.')
        return redirect('traspasos_lista')

    if request.method == 'POST':
        forma_pago = request.POST.get('forma_pago', traspaso.forma_pago or 'efectivo')
        with transaction.atomic():
            # 1. Descontar inventario en origen
            costo_total = Decimal('0')
            for det in traspaso.detalles.select_related('producto').all():
                inv, _ = Inventario.objects.get_or_create(
                    producto=det.producto,
                    sucursal=traspaso.sucursal_origen,
                    defaults={'stock_actual': 0, 'stock_minimo': 0, 'costo_promedio': det.costo_unitario},
                )
                antes = inv.stock_actual
                inv.stock_actual = max(inv.stock_actual - det.cantidad, 0)
                inv.save(update_fields=['stock_actual'])
                MovimientoInventario.objects.create(
                    inventario     = inv,
                    tipo           = 'traslado',
                    cantidad       = -det.cantidad,
                    stock_antes    = antes,
                    stock_despues  = inv.stock_actual,
                    costo_unitario = det.costo_unitario,
                    referencia     = traspaso.folio,
                    usuario        = request.user,
                    notas          = f'Salida por traspaso hacia {traspaso.sucursal_destino.nombre}',
                )
                costo_total += det.costo_unitario * det.cantidad

            # 2. Crear venta interna en el origen
            venta = Venta.objects.create(
                sucursal    = traspaso.sucursal_origen,
                cajero      = request.user,
                folio       = traspaso.folio,
                estado      = 'pagada',
                forma_pago  = forma_pago,
                subtotal    = traspaso.total,
                total       = traspaso.total,
                total_pagado= traspaso.total,
                costo_total = costo_total,
            )
            for det in traspaso.detalles.select_related('producto').all():
                DetalleVenta.objects.create(
                    venta          = venta,
                    producto       = det.producto,
                    cantidad       = det.cantidad,
                    precio_unitario= det.precio_traspaso_unit,
                    subtotal       = det.subtotal_traspaso,
                    costo_unitario = det.costo_unitario,
                )

            traspaso.estado       = 'aprobado'
            traspaso.aprobado_por = request.user
            traspaso.aprobado_en  = timezone.now()
            traspaso.pagado       = True
            traspaso.forma_pago   = forma_pago
            traspaso.venta_origen = venta
            traspaso.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'pagado', 'forma_pago', 'venta_origen'])

        from produccion.telegram import notificar_traspaso
        notificar_traspaso(traspaso, 'aprobado')
        messages.success(request, f'Traspaso {traspaso.folio} aprobado. Venta interna registrada en {traspaso.sucursal_origen.nombre}.')
        return redirect('traspasos_lista')

    return render(request, 'pos/traspaso_confirmar.html', {
        'traspaso': traspaso,
        'accion':   'aprobar',
    })


@login_required
def traspaso_recibir(request, pk):
    """Destino confirma recepción y puede ajustar cantidades recibidas."""
    traspaso = get_object_or_404(TraspasoSucursal, pk=pk)
    sucursal_user = _get_sucursal(request)

    puede = _es_admin(request.user) or (
        sucursal_user and sucursal_user == traspaso.sucursal_destino
    )
    if not puede:
        messages.error(request, 'Sin permiso para confirmar recepción.')
        return redirect('traspasos_lista')

    if traspaso.estado != 'aprobado':
        messages.error(request, f'El traspaso no está en camino (estado: {traspaso.get_estado_display()}).')
        return redirect('traspasos_lista')

    if request.method == 'POST':
        with transaction.atomic():
            for det in traspaso.detalles.select_related('producto').all():
                cant_rec = Decimal(request.POST.get(f'cant_{det.id}', det.cantidad))
                det.cantidad_recibida = cant_rec
                det.save(update_fields=['cantidad_recibida'])

                if cant_rec <= 0:
                    continue

                # Asegurar que exista PrecioPorSucursal en destino
                PrecioPorSucursal.objects.get_or_create(
                    producto=det.producto,
                    sucursal=traspaso.sucursal_destino,
                    defaults={
                        'precio_1': PrecioPorSucursal.objects.filter(
                            producto=det.producto
                        ).values_list('precio_1', flat=True).first() or Decimal('0'),
                    }
                )

                # Sumar inventario en destino
                inv_dest, _ = Inventario.objects.get_or_create(
                    producto=det.producto,
                    sucursal=traspaso.sucursal_destino,
                    defaults={'stock_actual': 0, 'stock_minimo': 0, 'costo_promedio': det.costo_unitario},
                )
                antes = inv_dest.stock_actual
                inv_dest.stock_actual += cant_rec
                # Actualizar costo promedio ponderado
                if inv_dest.costo_promedio and antes > 0:
                    inv_dest.costo_promedio = (
                        (inv_dest.costo_promedio * antes) + (det.costo_unitario * cant_rec)
                    ) / (antes + cant_rec)
                elif det.costo_unitario:
                    inv_dest.costo_promedio = det.costo_unitario
                inv_dest.save(update_fields=['stock_actual', 'costo_promedio'])

                MovimientoInventario.objects.create(
                    inventario     = inv_dest,
                    tipo           = 'traslado',
                    cantidad       = cant_rec,
                    stock_antes    = antes,
                    stock_despues  = inv_dest.stock_actual,
                    costo_unitario = det.costo_unitario,
                    referencia     = traspaso.folio,
                    usuario        = request.user,
                    notas          = f'Entrada por traspaso desde {traspaso.sucursal_origen.nombre}',
                )

            # Registrar gasto operativo en destino
            total_recibido = sum(
                det.precio_traspaso_unit * Decimal(request.POST.get(f'cant_{det.id}', det.cantidad))
                for det in traspaso.detalles.all()
            )
            GastoOperativo.objects.create(
                sucursal       = traspaso.sucursal_destino,
                tipo           = 'traspaso',
                descripcion    = f'Pago por traspaso {traspaso.folio} recibido de {traspaso.sucursal_origen.nombre}',
                monto          = total_recibido,
                registrado_por = request.user,
                referencia     = traspaso.folio,
            )

            traspaso.estado       = 'recibido'
            traspaso.recibido_por = request.user
            traspaso.recibido_en  = timezone.now()
            traspaso.save(update_fields=['estado', 'recibido_por', 'recibido_en'])

        from produccion.telegram import notificar_traspaso
        notificar_traspaso(traspaso, 'recibido')
        messages.success(request, f'Traspaso {traspaso.folio} recibido. Gasto de ${total_recibido} registrado en {traspaso.sucursal_destino.nombre}.')
        return redirect('traspasos_lista')

    return render(request, 'pos/traspaso_confirmar.html', {
        'traspaso': traspaso,
        'accion':   'recibir',
    })


@login_required
def traspaso_cancelar(request, pk):
    traspaso = get_object_or_404(TraspasoSucursal, pk=pk)
    if not _es_admin(request.user):
        messages.error(request, 'Solo el administrador puede cancelar traspasos.')
        return redirect('traspasos_lista')
    if traspaso.estado in ('recibido', 'cancelado'):
        messages.error(request, 'No se puede cancelar en este estado.')
        return redirect('traspasos_lista')
    if request.method == 'POST':
        # Si ya estaba aprobado, devolver stock a origen
        if traspaso.estado == 'aprobado':
            with transaction.atomic():
                for det in traspaso.detalles.select_related('producto').all():
                    inv, _ = Inventario.objects.get_or_create(
                        producto=det.producto, sucursal=traspaso.sucursal_origen,
                        defaults={'stock_actual': 0, 'stock_minimo': 0, 'costo_promedio': det.costo_unitario},
                    )
                    antes = inv.stock_actual
                    inv.stock_actual += det.cantidad
                    inv.save(update_fields=['stock_actual'])
                    MovimientoInventario.objects.create(
                        inventario=inv, tipo='ajuste', cantidad=det.cantidad,
                        stock_antes=antes, stock_despues=inv.stock_actual,
                        costo_unitario=det.costo_unitario, referencia=traspaso.folio,
                        usuario=request.user,
                        notas=f'Reintegro por cancelación de traspaso {traspaso.folio}',
                    )
        traspaso.estado = 'cancelado'
        traspaso.save(update_fields=['estado'])
        from produccion.telegram import notificar_traspaso
        notificar_traspaso(traspaso, 'cancelado')
        messages.success(request, f'Traspaso {traspaso.folio} cancelado.')
        return redirect('traspasos_lista')

    return render(request, 'pos/traspaso_confirmar.html', {
        'traspaso': traspaso,
        'accion':   'cancelar',
    })


@login_required
@require_GET
def traspaso_productos_api(request):
    """Devuelve productos con stock disponible en una sucursal (para el formulario nuevo)."""
    suc_id = request.GET.get('sucursal')
    q      = request.GET.get('q', '')
    if not suc_id:
        return JsonResponse({'productos': []})

    inv_qs = Inventario.objects.filter(
        sucursal_id=suc_id, stock_actual__gt=0
    ).select_related('producto__categoria')
    if q:
        inv_qs = inv_qs.filter(
            Q(producto__nombre__icontains=q) | Q(producto__codigo__icontains=q)
        )
    data = [
        {
            'id':     inv.producto_id,
            'nombre': inv.producto.nombre,
            'codigo': inv.producto.codigo,
            'stock':  float(inv.stock_actual),
            'unidad': inv.producto.unidad,
        }
        for inv in inv_qs[:30]
    ]
    return JsonResponse({'productos': data})


@login_required
@require_POST
def actualizar_precio(request, pp_id):
    """Guarda precios de un PrecioPorSucursal vía AJAX."""
    if not _es_admin(request.user):
        return JsonResponse({'ok': False}, status=403)
    pp = get_object_or_404(PrecioPorSucursal, pk=pp_id)
    try:
        data = json.loads(request.body)
        campos = {}
        for campo in ('precio_1', 'precio_2', 'precio_3', 'precio_oferta', 'precio_traspaso'):
            v = data.get(campo)
            if v is not None:
                campos[campo] = Decimal(str(v)) if v != '' else None
        if 'en_oferta' in data:
            campos['en_oferta'] = bool(data['en_oferta'])
        for k, v in campos.items():
            setattr(pp, k, v)
        pp.save(update_fields=list(campos.keys()))
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@login_required
def editar_producto(request, pk):
    if not _es_admin(request.user):
        return redirect('pos')
    producto   = get_object_or_404(ProductoPOS, pk=pk)
    categorias = CategoriaPOS.objects.all().order_by('nombre')

    if request.method == 'POST':
        producto.nombre      = request.POST.get('nombre', '').strip()
        producto.codigo      = request.POST.get('codigo', '').strip()
        producto.categoria_id = request.POST.get('categoria') or None
        producto.descripcion = request.POST.get('descripcion', '').strip()
        producto.unidad      = request.POST.get('unidad', 'pieza').strip()
        try:
            producto.peso = Decimal(request.POST.get('peso', '0').strip() or '0')
        except Exception:
            producto.peso = Decimal('0')
        if request.FILES.get('imagen'):
            producto.imagen = request.FILES['imagen']
        producto.activo = request.POST.get('activo') == '1'
        producto.save()
        messages.success(request, f'Producto "{producto.nombre}" actualizado.')
        return redirect('pos_productos_lista')

    unidades = ['pieza', 'caja', 'paquete', 'kg', 'litro', 'metro', 'par', 'docena', 'resma']
    return render(request, 'pos/crear_producto.html', {
        'categorias': categorias,
        'producto':   producto,
        'post':       {},
        'unidades':   unidades,
    })


# ── ENTRADA MANUAL DE MERCANCÍA ───────────────────────────
@login_required
def entrada_mercancia(request):
    """Vista para agregar stock manualmente (ajuste o entrada sin compra formal)."""
    sucursal = _get_sucursal(request)
    if not sucursal and not _es_admin(request.user):
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('pos')

    if _es_admin(request.user):
        sucursal_id = request.GET.get('sucursal') or request.POST.get('sucursal')
        if sucursal_id:
            sucursal = get_object_or_404(Sucursal, pk=sucursal_id)

    if request.method == 'POST':
        tipo       = request.POST.get('tipo', 'entrada')
        referencia = request.POST.get('referencia', '').strip()
        notas      = request.POST.get('notas', '').strip()

        # Recibir listas de productos (multi-producto por ticket)
        producto_ids = request.POST.getlist('producto_id[]')
        cantidades   = request.POST.getlist('cantidad[]')
        costos       = request.POST.getlist('costo_unitario[]')

        if not producto_ids:
            messages.error(request, 'Agrega al menos un producto al ticket.')
            return redirect(request.path + (f'?sucursal={sucursal.id}' if sucursal else ''))

        ref_final = referencia or f'Entrada manual — {request.user.username}'
        registrados = []
        errores     = []

        with transaction.atomic():
            for pid, cant_str, costo_str in zip(producto_ids, cantidades, costos):
                try:
                    producto = ProductoPOS.objects.get(pk=pid)
                    cantidad = Decimal(cant_str or '0')
                    costo    = Decimal(costo_str or '0')
                    if cantidad <= 0:
                        errores.append(f'{producto.nombre}: cantidad debe ser > 0')
                        continue
                except Exception as e:
                    errores.append(str(e))
                    continue

                inv, _ = Inventario.objects.get_or_create(
                    producto=producto, sucursal=sucursal,
                    defaults={'stock_actual': 0, 'costo_promedio': costo},
                )
                stock_antes = inv.stock_actual
                if costo > 0:
                    stock_nuevo = inv.stock_actual + cantidad
                    if stock_nuevo > 0:
                        inv.costo_promedio = (
                            (inv.stock_actual * inv.costo_promedio) + (cantidad * costo)
                        ) / stock_nuevo
                inv.stock_actual += cantidad
                inv.save()

                MovimientoInventario.objects.create(
                    inventario=inv, tipo=tipo,
                    cantidad=cantidad, stock_antes=stock_antes,
                    stock_despues=inv.stock_actual,
                    costo_unitario=costo,
                    referencia=ref_final,
                    usuario=request.user,
                    notas=notas,
                )
                registrados.append(f'{cantidad} × {producto.nombre}')

        if registrados:
            messages.success(request, f'✅ Ticket registrado: {", ".join(registrados)}.')
        for e in errores:
            messages.warning(request, f'⚠️ {e}')

        url = reverse('entrada_mercancia') + (f'?sucursal={sucursal.id}' if sucursal else '')
        return redirect(url)

    # GET — listar últimos movimientos de entrada/ajuste para referencia
    productos = ProductoPOS.objects.filter(activo=True).order_by('nombre')
    ultimos = MovimientoInventario.objects.filter(
        inventario__sucursal=sucursal,
        tipo__in=['entrada', 'ajuste'],
    ).select_related('inventario__producto', 'usuario').order_by('-fecha')[:20] if sucursal else []

    sucursales = Sucursal.objects.filter(activa=True) if _es_admin(request.user) else []

    import json as _json
    productos_json = _json.dumps([
        {'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo, 'unidad': p.unidad}
        for p in productos
    ])

    return render(request, 'pos/entrada_mercancia.html', {
        'sucursal':      sucursal,
        'sucursales':    sucursales,
        'productos':     productos,
        'productos_json': productos_json,
        'ultimos':       ultimos,
    })


# ── TOP PRODUCTOS (API para POS) ─────────────────────────
@login_required
@require_GET
def top_productos_api(request):
    sucursal = _get_sucursal(request)
    periodo  = request.GET.get('periodo', 'dia')  # dia | semana | mes
    hoy      = date.today()

    if periodo == 'dia':
        desde = hoy
    elif periodo == 'semana':
        desde = hoy - timedelta(days=hoy.weekday())
    else:
        desde = hoy.replace(day=1)

    qs = DetalleVenta.objects.filter(
        venta__creado__date__gte=desde,
        venta__estado__in=['pagada', 'credito'],
    )
    if sucursal:
        qs = qs.filter(venta__sucursal=sucursal)

    top = list(
        qs.values('producto__id', 'producto__nombre', 'producto__codigo')
          .annotate(total_uds=Sum('cantidad'), total_pesos=Sum('subtotal'))
          .order_by('-total_uds')[:15]
    )

    # Enriquecer con precio y stock para mostrarlo como tiles en el POS
    if sucursal and top:
        ids = [t['producto__id'] for t in top]
        precios_m = {
            pp.producto_id: pp
            for pp in PrecioPorSucursal.objects.filter(
                producto_id__in=ids, sucursal=sucursal, activo=True
            )
        }
        inv_m = {
            inv.producto_id: inv
            for inv in Inventario.objects.filter(producto_id__in=ids, sucursal=sucursal)
        }
        imgs_m = {
            p.id: p.imagen.url if p.imagen else None
            for p in ProductoPOS.objects.filter(pk__in=ids)
        }
        for t in top:
            pid = t['producto__id']
            pp  = precios_m.get(pid)
            inv = inv_m.get(pid)
            t['precio_1']      = float(pp.precio_1)      if pp else 0
            t['precio_2']      = float(pp.precio_2)      if pp and pp.precio_2 else None
            t['precio_3']      = float(pp.precio_3)      if pp and pp.precio_3 else None
            t['en_oferta']     = pp.en_oferta            if pp else False
            t['precio_oferta'] = float(pp.precio_oferta) if pp and pp.precio_oferta else None
            t['stock']         = float(inv.stock_actual) if inv else 0
            t['costo']         = float(inv.costo_promedio) if inv else 0
            t['imagen']        = imgs_m.get(pid)

    return JsonResponse({'top': top})


# ── RECARGAS Y PAGOS DE SERVICIO ─────────────────────────

@login_required
def servicios_view(request):
    sucursal = _get_sucursal(request)
    if not sucursal:
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('pos')

    if request.method == 'POST':
        tipo      = request.POST.get('tipo')
        monto_str = request.POST.get('monto', '0').strip()
        com_str   = request.POST.get('comision', '1').strip()
        try:
            monto    = Decimal(monto_str)
            comision = Decimal(com_str)
        except Exception:
            messages.error(request, 'Monto o comisión inválidos.')
            return redirect('servicios_pos')

        TransaccionServicio.objects.create(
            sucursal   = sucursal,
            cajero     = request.user,
            tipo       = tipo,
            servicio   = request.POST.get('servicio', ''),
            telefono   = request.POST.get('telefono', '').strip(),
            referencia = request.POST.get('referencia', '').strip(),
            monto      = monto,
            comision   = comision,
            notas      = request.POST.get('notas', '').strip(),
        )
        messages.success(request, f'{"Recarga" if tipo == "recarga" else "Pago"} de ${monto} registrado. Comisión: ${comision}.')
        return redirect('servicios_pos')

    hoy = TransaccionServicio.objects.filter(
        sucursal=sucursal, fecha__date=date.today()
    ).order_by('-fecha')

    total_recargas  = hoy.filter(tipo='recarga').aggregate(t=Sum('comision'))['t'] or Decimal('0')
    total_servicios = hoy.filter(tipo='servicio').aggregate(t=Sum('comision'))['t'] or Decimal('0')

    return render(request, 'pos/servicios.html', {
        'sucursal':        sucursal,
        'transacciones':   hoy,
        'total_recargas':  total_recargas,
        'total_servicios': total_servicios,
        'total_comisiones': total_recargas + total_servicios,
    })


@login_required
@require_POST
def servicio_eliminar(request, pk):
    """Solo el mismo cajero o admin puede eliminar en el mismo día."""
    t = get_object_or_404(TransaccionServicio, pk=pk)
    sucursal = _get_sucursal(request)
    if not (_es_admin(request.user) or
            (t.cajero == request.user and t.fecha.date() == date.today())):
        return JsonResponse({'ok': False, 'error': 'Sin permiso'})
    t.delete()
    return JsonResponse({'ok': True})


# ── CAJA DIARIA ──────────────────────────────────────────

def _get_caja_hoy(sucursal):
    """Devuelve la caja abierta de hoy para la sucursal, o None."""
    return CierreCaja.objects.filter(
        sucursal=sucursal, fecha=date.today(), estado='abierta'
    ).first()


@login_required
def apertura_caja(request):
    sucursal = _get_sucursal(request)
    if not sucursal:
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('pos')

    caja_hoy = CierreCaja.objects.filter(sucursal=sucursal, fecha=date.today()).first()
    if caja_hoy:
        messages.info(request, f'La caja ya fue abierta hoy con cambio inicial de ${caja_hoy.cambio_inicial}.')
        return redirect('pos')

    if request.method == 'POST':
        cambio = Decimal(request.POST.get('cambio_inicial', '0') or '0')
        _, creada = CierreCaja.objects.get_or_create(
            sucursal=sucursal,
            fecha=date.today(),
            defaults={
                'cambio_inicial':   cambio,
                'usuario_apertura': request.user,
            }
        )
        if creada:
            messages.success(request, f'Caja abierta con cambio inicial de ${cambio}.')
        else:
            messages.info(request, 'La caja ya estaba abierta hoy.')
        return redirect('pos')

    return render(request, 'pos/apertura_caja.html', {'sucursal': sucursal})


@login_required
@require_POST
def retiro_efectivo(request):
    sucursal = _get_sucursal(request)
    if not sucursal:
        return JsonResponse({'ok': False, 'error': 'Sin sucursal'})

    caja = _get_caja_hoy(sucursal)
    if not caja:
        return JsonResponse({'ok': False, 'error': 'No hay caja abierta hoy'})

    try:
        data   = json.loads(request.body)
        monto  = Decimal(str(data.get('monto', 0)))
        motivo = data.get('motivo', '').strip()
        if monto <= 0:
            return JsonResponse({'ok': False, 'error': 'Monto inválido'})
        if not motivo:
            return JsonResponse({'ok': False, 'error': 'Ingresa el motivo del retiro'})
        RetiroEfectivo.objects.create(caja=caja, monto=monto, motivo=motivo, usuario=request.user)
        total_retiros = caja.retiros.aggregate(t=Sum('monto'))['t'] or 0
        return JsonResponse({'ok': True, 'total_retiros': float(total_retiros)})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@login_required
def cierre_caja(request):
    sucursal = _get_sucursal(request)
    if not sucursal:
        messages.error(request, 'No tienes sucursal asignada.')
        return redirect('pos')

    caja     = _get_caja_hoy(sucursal)
    sin_caja = caja is None

    if not sin_caja and request.method == 'POST':
        pass  # procesado abajo
    elif sin_caja and request.method == 'POST':
        messages.error(request, 'No hay caja abierta hoy.')
        return redirect('cierre_caja')

    cambio_inicial = caja.cambio_inicial if caja else Decimal('0')

    # Calcular totales del día
    ventas_hoy = Venta.objects.filter(
        sucursal=sucursal, creado__date=date.today(), estado='pagada', forma_pago='efectivo'
    )
    total_ventas_efectivo = ventas_hoy.aggregate(t=Sum('total'))['t'] or Decimal('0')
    total_retiros         = (caja.retiros.aggregate(t=Sum('monto'))['t'] or Decimal('0')) if caja else Decimal('0')
    gastos_hoy            = GastoOperativo.objects.filter(
        sucursal=sucursal, fecha__date=date.today()
    )
    total_gastos_efectivo = gastos_hoy.aggregate(t=Sum('monto'))['t'] or Decimal('0')

    # Recargas y pagos de servicio del día
    servicios_hoy = TransaccionServicio.objects.filter(
        sucursal=sucursal, fecha__date=date.today()
    ).order_by('-fecha')
    totales_srv      = servicios_hoy.aggregate(m=Sum('monto'), c=Sum('comision'))
    total_monto_servicios = totales_srv['m'] or Decimal('0')
    total_comisiones      = totales_srv['c'] or Decimal('0')

    # efectivo esperado = cambio_inicial + ventas_mercancia + monto_recargas_servicios - retiros - gastos
    # (el monto completo de recargas/servicios entra físicamente a la caja)
    efectivo_esperado = (cambio_inicial + total_ventas_efectivo
                         + total_monto_servicios - total_retiros - total_gastos_efectivo)

    if request.method == 'POST' and caja:
        efectivo_contado = Decimal(request.POST.get('efectivo_contado', '0') or '0')
        diferencia       = efectivo_contado - efectivo_esperado
        with transaction.atomic():
            caja.efectivo_contado      = efectivo_contado
            caja.usuario_cierre        = request.user
            caja.cierre_en             = timezone.now()
            caja.notas_cierre          = request.POST.get('notas_cierre', '')
            caja.estado                = 'cerrada'
            caja.total_ventas_efectivo = total_ventas_efectivo
            caja.total_retiros         = total_retiros
            caja.total_gastos_efectivo = total_gastos_efectivo
            caja.total_monto_servicios = total_monto_servicios
            caja.total_comisiones      = total_comisiones
            caja.efectivo_esperado     = efectivo_esperado
            caja.diferencia            = diferencia
            caja.save()
        estado = 'sobra' if diferencia > 0 else ('falta' if diferencia < 0 else 'exacto')
        messages.success(request, f'Caja cerrada. {estado.capitalize()}: ${abs(diferencia)}.')
        return redirect('resumen_cierre_caja', pk=caja.pk)

    retiros = caja.retiros.all() if caja else RetiroEfectivo.objects.none()
    return render(request, 'pos/cierre_caja.html', {
        'caja':                   caja,
        'sin_caja':               sin_caja,
        'sucursal':               sucursal,
        'cambio_inicial':         cambio_inicial,
        'total_ventas_efectivo':  total_ventas_efectivo,
        'total_retiros':          total_retiros,
        'total_gastos_efectivo':  total_gastos_efectivo,
        'total_monto_servicios':  total_monto_servicios,
        'total_comisiones':       total_comisiones,
        'servicios_hoy':          servicios_hoy,
        'efectivo_esperado':      efectivo_esperado,
        'retiros':                retiros,
        'gastos_hoy':             gastos_hoy,
    })


@login_required
def revisar_cierre_caja(request, pk):
    caja = get_object_or_404(CierreCaja, pk=pk)
    sucursal_user = _get_sucursal(request)
    us = request.user.sucursales_pos.filter(activo=True, sucursal=caja.sucursal).first()
    es_admin = _es_admin(request.user)
    es_gerente = us and us.rol == 'gerente'

    if not es_admin and not es_gerente:
        messages.error(request, 'No tienes permiso para revisar cierres.')
        return redirect('pos')

    if request.method == 'POST' and caja.estado == 'cerrada':
        caja.revisado_por   = request.user
        caja.revisado_en    = timezone.now()
        caja.notas_revision = request.POST.get('notas_revision', '').strip()
        caja.save(update_fields=['revisado_por', 'revisado_en', 'notas_revision'])
        messages.success(request, f'Cierre de {caja.sucursal.nombre} del {caja.fecha} marcado como revisado.')

    return redirect('resumen_cierre_caja', pk=pk)


@login_required
def resumen_cierre_caja(request, pk):
    caja = get_object_or_404(CierreCaja, pk=pk)
    sucursal_user = _get_sucursal(request)
    puede = _es_admin(request.user) or (sucursal_user and sucursal_user == caja.sucursal)
    if not puede:
        return redirect('pos')

    servicios = TransaccionServicio.objects.filter(
        sucursal=caja.sucursal, fecha__date=caja.fecha
    ).order_by('fecha')
    total_monto_servicios = servicios.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_comisiones      = servicios.aggregate(t=Sum('comision'))['t'] or Decimal('0')

    retiros = caja.retiros.all().order_by('fecha')

    es_admin  = _es_admin(request.user)
    us        = request.user.sucursales_pos.filter(activo=True, sucursal=caja.sucursal).first()
    es_gerente = us and us.rol == 'gerente'
    puede_revisar = (es_admin or es_gerente) and caja.estado == 'cerrada' and not caja.revisado_por

    return render(request, 'pos/resumen_cierre_caja.html', {
        'caja':                  caja,
        'servicios':             servicios,
        'total_monto_servicios': total_monto_servicios,
        'total_comisiones':      total_comisiones,
        'retiros':               retiros,
        'es_admin':              es_admin,
        'puede_revisar':         puede_revisar,
    })


@login_required
def historial_cierres(request):
    es_admin = _es_admin(request.user)
    sucursal_user = _get_sucursal(request)
    us = request.user.sucursales_pos.filter(activo=True).select_related('sucursal').first()
    rol = us.rol if us else None

    if not es_admin and rol not in ('gerente',):
        return redirect('pos')

    # Filtros
    sucursal_id = request.GET.get('sucursal')
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')

    qs = CierreCaja.objects.select_related('sucursal', 'usuario_apertura', 'usuario_cierre', 'revisado_por').order_by('-fecha', 'sucursal__nombre')

    if not es_admin and sucursal_user:
        qs = qs.filter(sucursal=sucursal_user)
    elif sucursal_id:
        qs = qs.filter(sucursal_id=sucursal_id)

    if fecha_desde:
        try:
            qs = qs.filter(fecha__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(fecha__lte=fecha_hasta)
        except Exception:
            pass

    sucursales_lista = Sucursal.objects.filter(activa=True) if es_admin else []

    return render(request, 'pos/historial_cierres.html', {
        'cierres':         qs[:90],
        'sucursales':      sucursales_lista,
        'sucursal_sel':    sucursal_id,
        'fecha_desde':     fecha_desde,
        'fecha_hasta':     fecha_hasta,
        'es_admin':        es_admin,
    })


# ── VENTAS CANCELADAS ────────────────────────────────────
@login_required
def ventas_canceladas(request):
    sucursal = _get_sucursal(request)

    # Admin puede filtrar por cualquier sucursal
    if _es_admin(request.user):
        suc_id = request.GET.get('sucursal')
        if suc_id:
            sucursal = get_object_or_404(Sucursal, pk=suc_id)

    # Cajero/vendedor solo ve su sucursal
    us_pos = request.user.sucursales_pos.filter(activo=True).first()
    rol_pos = us_pos.rol if us_pos else ('admin' if _es_admin(request.user) else None)

    from datetime import date, datetime, timedelta
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else None
    except ValueError:
        fecha = None

    ventas = Venta.objects.filter(estado='cancelada').select_related('cajero', 'sucursal').prefetch_related('detalles__producto').order_by('-creado')

    if sucursal:
        ventas = ventas.filter(sucursal=sucursal)
    if fecha:
        ventas = ventas.filter(creado__date=fecha)

    sucursales = Sucursal.objects.filter(activa=True) if _es_admin(request.user) else []

    return render(request, 'pos/ventas_canceladas.html', {
        'ventas':     ventas,
        'sucursal':   sucursal,
        'sucursales': sucursales,
        'fecha':      fecha,
        'rol_pos':    rol_pos,
        'ver_ganancia': rol_pos in ('gerente', 'admin') or _es_admin(request.user),
    })


# ── INGRESOS DEL DÍA ─────────────────────────────────────
@login_required
def ingresos_dia(request):
    sucursal = _get_sucursal(request)
    if _es_admin(request.user):
        suc_id = request.GET.get('sucursal')
        if suc_id:
            sucursal = get_object_or_404(Sucursal, pk=suc_id)

    from datetime import date, datetime
    # Filtros
    fecha_str = request.GET.get('fecha', '')
    folio_q   = request.GET.get('folio', '').strip()
    forma_q   = request.GET.get('forma_pago', '')

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else date.today()
    except ValueError:
        fecha = date.today()

    ventas = Venta.objects.filter(
        creado__date=fecha, estado__in=['pagada', 'credito']
    ).select_related('cajero', 'sucursal').prefetch_related('detalles__producto')

    if sucursal:
        ventas = ventas.filter(sucursal=sucursal)
    if folio_q:
        ventas = ventas.filter(folio__icontains=folio_q)
    if forma_q:
        ventas = ventas.filter(forma_pago=forma_q)

    ventas = ventas.order_by('-creado')

    # Totales
    totales = ventas.aggregate(
        total_ventas=Sum('total'),
        total_costo=Sum('costo_total'),
        total_descuentos=Sum('descuento'),
    )
    total_ventas     = totales['total_ventas']     or Decimal('0')
    total_costo      = totales['total_costo']      or Decimal('0')
    total_descuentos = totales['total_descuentos'] or Decimal('0')
    ganancia_dia     = total_ventas - total_costo - total_descuentos

    # Desglose por forma de pago
    from django.db.models import Count
    por_forma = ventas.values('forma_pago').annotate(
        subtotal=Sum('total'), num=Count('id')
    ).order_by('-subtotal')

    sucursales = Sucursal.objects.filter(activa=True) if _es_admin(request.user) else []

    # Rol del usuario en el POS (para ocultar info financiera al cajero)
    us_pos = request.user.sucursales_pos.filter(activo=True).first()
    rol_pos = us_pos.rol if us_pos else ('admin' if _es_admin(request.user) else None)
    ver_ganancia = rol_pos in ('gerente', 'admin') or _es_admin(request.user)

    return render(request, 'pos/ingresos_dia.html', {
        'ventas':          ventas,
        'fecha':           fecha,
        'folio_q':         folio_q,
        'forma_q':         forma_q,
        'total_ventas':    total_ventas,
        'total_costo':     total_costo,
        'total_descuentos': total_descuentos,
        'ganancia_dia':    ganancia_dia,
        'por_forma':       por_forma,
        'sucursal':        sucursal,
        'sucursales':      sucursales,
        'formas_pago':     Venta.PAGO_CHOICES,
        'ver_ganancia':    ver_ganancia,
    })


# ── DASHBOARD DE SUCURSALES ───────────────────────────────
@login_required
def dashboard_sucursales(request):
    if not _es_admin(request.user):
        messages.error(request, 'Sin permisos.')
        return redirect('pos')

    from django.contrib.auth import get_user_model
    from datetime import date

    Usuario = get_user_model()
    hoy         = date.today()
    inicio_mes  = hoy.replace(day=1)

    # Si el usuario tiene asignaciones en sucursales, solo ve las suyas aunque sea admin
    asignaciones = UsuarioSucursal.objects.filter(usuario=request.user, activo=True).values_list('sucursal_id', flat=True)
    if asignaciones.exists() and not request.user.is_superuser:
        sucursales_qs = Sucursal.objects.filter(activa=True, id__in=asignaciones).select_related('cliente')
    else:
        sucursales_qs = Sucursal.objects.filter(activa=True).select_related('cliente')

    sucursal_sel_id = request.GET.get('suc')

    datos = []
    for suc in sucursales_qs:
        qs_hoy = Venta.objects.filter(sucursal=suc, creado__date=hoy, estado__in=['pagada','credito'])
        ventas_hoy = {'total': qs_hoy.aggregate(t=Sum('total'))['t'], 'num': qs_hoy.count()}
        ventas_mes = Venta.objects.filter(
            sucursal=suc, creado__date__gte=inicio_mes, estado__in=['pagada','credito']
        ).aggregate(total=Sum('total'), costo=Sum('costo_total'))

        criticos = Inventario.objects.filter(
            sucursal=suc,
            stock_actual__lte=F('stock_minimo'),
            stock_minimo__gt=0,
        ).count()

        usuarios_suc = UsuarioSucursal.objects.filter(
            sucursal=suc, activo=True
        ).select_related('usuario')

        # Últimas 5 ventas
        ultimas_ventas = Venta.objects.filter(
            sucursal=suc, estado__in=['pagada','credito']
        ).select_related('cajero').order_by('-creado')[:5]

        # Inventario crítico detalle
        inv_criticos = Inventario.objects.filter(
            sucursal=suc,
            stock_actual__lte=F('stock_minimo'),
            stock_minimo__gt=0,
        ).select_related('producto').order_by('stock_actual')[:10]

        venta_mes_total = ventas_mes['total'] or Decimal('0')
        costo_mes_total = ventas_mes['costo']  or Decimal('0')
        datos.append({
            'sucursal':      suc,
            'venta_hoy':     ventas_hoy['total'] or Decimal('0'),
            'num_hoy':       ventas_hoy['num'],
            'venta_mes':     venta_mes_total,
            'ganancia_mes':  venta_mes_total - costo_mes_total,
            'criticos':      criticos,
            'usuarios':      usuarios_suc,
            'ultimas_ventas': ultimas_ventas,
            'inv_criticos':  inv_criticos,
        })

    # Todos los usuarios disponibles para asignar
    todos_usuarios = Usuario.objects.filter(is_active=True).order_by('first_name','username')

    # Sucursal seleccionada (para tab activo)
    if sucursal_sel_id == 'comparar':
        suc_activa = 'comparar'
    else:
        try:
            suc_activa = int(sucursal_sel_id) if sucursal_sel_id else None
        except (ValueError, TypeError):
            suc_activa = None
        if suc_activa is None and datos:
            suc_activa = datos[0]['sucursal'].id

    total_hoy      = sum(d['venta_hoy']    for d in datos)
    total_mes      = sum(d['venta_mes']    for d in datos)
    total_ganancia = sum(d['ganancia_mes'] for d in datos)
    total_criticos = sum(d['criticos']     for d in datos)

    return render(request, 'pos/dashboard_sucursales.html', {
        'datos':          datos,
        'suc_activa':     suc_activa,
        'todos_usuarios': todos_usuarios,
        'roles':          UsuarioSucursal.ROL_CHOICES,
        'hoy':            hoy,
        'inicio_mes':     inicio_mes,
        'total_hoy':      total_hoy,
        'total_mes':      total_mes,
        'total_ganancia': total_ganancia,
        'total_criticos': total_criticos,
    })


@login_required
@require_POST
def asignar_usuario_sucursal(request, suc_pk):
    if not _es_admin(request.user):
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    from django.contrib.auth import get_user_model
    Usuario  = get_user_model()
    sucursal = get_object_or_404(Sucursal, pk=suc_pk)
    usuario  = get_object_or_404(Usuario, pk=request.POST.get('usuario_id'))
    rol      = request.POST.get('rol', 'cajero')

    us, created = UsuarioSucursal.objects.update_or_create(
        usuario=usuario, sucursal=sucursal,
        defaults={'rol': rol, 'activo': True},
    )
    messages.success(request, f'{usuario.get_full_name() or usuario.username} asignado como {us.get_rol_display()} en {sucursal.nombre}.')
    return redirect(f'{request.META.get("HTTP_REFERER", "/pos/sucursales/")}#suc-{suc_pk}')


@login_required
@require_POST
def quitar_usuario_sucursal(request, pk):
    if not _es_admin(request.user):
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    us = get_object_or_404(UsuarioSucursal, pk=pk)
    nombre  = us.usuario.get_full_name() or us.usuario.username
    sucursal_id = us.sucursal_id
    us.delete()
    messages.success(request, f'{nombre} removido de la sucursal.')
    return redirect(f'{request.META.get("HTTP_REFERER", "/pos/sucursales/")}#suc-{sucursal_id}')


# ── API BARRIDO MANUAL ────────────────────────────────────
@login_required
def barrido_manual(request):
    if not _es_admin(request.user):
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    from .tasks import barrido_inventario_critico
    barrido_inventario_critico()
    messages.success(request, 'Barrido de inventario ejecutado. Revisa Telegram.')
    return redirect('dashboard_admin_pos')


# ── DASHBOARD SUCURSAL (gerente/vendedor/almacén/cajero) ──────────────────────
@login_required
def dashboard_sucursal(request):
    from datetime import date
    from django.db.models import Sum, Count

    us = request.user.sucursales_pos.filter(activo=True).select_related('sucursal').first()
    if not us:
        messages.error(request, 'No tienes ninguna sucursal asignada.')
        return redirect('home')

    sucursal = us.sucursal
    rol      = us.rol
    hoy      = date.today()

    # Ventas del día
    ventas_hoy = Venta.objects.filter(sucursal=sucursal, creado__date=hoy)
    total_hoy  = ventas_hoy.aggregate(t=Sum('total'))['t'] or 0
    num_ventas = ventas_hoy.count()

    # Últimas 5 ventas
    ultimas_ventas = ventas_hoy.select_related('cajero').order_by('-creado')[:5]

    # Stock crítico de esta sucursal
    from .models import Inventario
    criticos = Inventario.objects.filter(
        sucursal=sucursal, stock_actual__lte=F('stock_minimo'), stock_minimo__gt=0
    ).select_related('producto').order_by('stock_actual')[:8]

    # Equipo de la sucursal
    equipo = UsuarioSucursal.objects.filter(
        sucursal=sucursal, activo=True
    ).select_related('usuario').order_by('rol')

    caja_hoy = _get_caja_hoy(sucursal)

    return render(request, 'pos/dashboard_sucursal.html', {
        'sucursal':      sucursal,
        'rol':           rol,
        'hoy':           hoy,
        'total_hoy':     total_hoy,
        'num_ventas':    num_ventas,
        'ultimas_ventas': ultimas_ventas,
        'criticos':      criticos,
        'caja_hoy':      caja_hoy,
        'equipo':        equipo,
    })


# ── CANCELACIÓN DE VENTAS ─────────────────────────────────
@login_required
@require_POST
def cancelar_venta(request, venta_pk):
    """Cancela una venta verificando el PIN de un supervisor/gerente/admin."""
    from django.contrib.auth import authenticate, get_user_model
    Usuario = get_user_model()

    try:
        data = json.loads(request.body)
        pin  = data.get('pin', '').strip()
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Solicitud inválida.'})

    if not pin:
        return JsonResponse({'ok': False, 'error': 'PIN requerido.'})

    venta = get_object_or_404(Venta, pk=venta_pk)
    if venta.estado == 'cancelada':
        return JsonResponse({'ok': False, 'error': 'La venta ya está cancelada.'})

    # Buscar un supervisor con ese PIN en la misma sucursal
    supervisor = None
    candidatos = UsuarioSucursal.objects.filter(
        sucursal=venta.sucursal, activo=True, rol__in=['gerente']
    ).select_related('usuario')
    for us in candidatos:
        user_auth = authenticate(request, username=us.usuario.username, password=pin)
        if user_auth:
            supervisor = user_auth
            break

    # Si no hay gerente local, aceptar admin/superuser
    if not supervisor:
        for u in Usuario.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(rol='admin')
        ):
            user_auth = authenticate(request, username=u.username, password=pin)
            if user_auth:
                supervisor = user_auth
                break

    if not supervisor:
        return JsonResponse({'ok': False, 'error': 'PIN incorrecto o sin permisos de supervisor.'})

    # Restaurar inventario y cancelar
    with transaction.atomic():
        for det in venta.detalles.select_related('producto').all():
            inv = Inventario.objects.filter(
                producto=det.producto, sucursal=venta.sucursal
            ).first()
            if inv:
                inv.stock_actual += det.cantidad
                inv.save(update_fields=['stock_actual'])
                MovimientoInventario.objects.create(
                    inventario=inv, tipo='entrada',
                    cantidad=det.cantidad,
                    stock_antes=inv.stock_actual - det.cantidad,
                    stock_despues=inv.stock_actual,
                    notas=f'Cancelación venta {venta.folio} — autorizado por {supervisor.get_full_name() or supervisor.username}',
                )
        venta.estado = 'cancelada'
        venta.save(update_fields=['estado'])

    return JsonResponse({'ok': True})


@login_required
@require_POST
def solicitar_cancelacion_telegram(request, venta_pk):
    """Crea token temporal y envía botón en Telegram para autorizar cancelación."""
    import secrets
    from django.conf import settings as dj_settings
    from produccion.telegram import _api_post

    venta  = get_object_or_404(Venta, pk=venta_pk)
    cajero = request.user.get_full_name() or request.user.username

    # Invalidar solicitudes previas pendientes para esta venta
    SolicitudCancelacion.objects.filter(venta=venta, usado=False).update(usado=True)

    token = secrets.token_urlsafe(32)
    SolicitudCancelacion.objects.create(venta=venta, token=token, solicitado_por=request.user)

    site_url = getattr(dj_settings, 'SITE_URL', 'http://localhost:8000')
    url_auth = f"{site_url}/pos/autorizar-cancelacion/{token}/"

    chat_id = getattr(dj_settings, 'TELEGRAM_CHAT_ID', '')
    try:
        result = _api_post('sendMessage', {
            'chat_id': chat_id,
            'text': (
                f"🚫 <b>Solicitud de cancelación</b>\n\n"
                f"🧾 Folio: <b>{venta.folio}</b>\n"
                f"🏪 Sucursal: {venta.sucursal.nombre}\n"
                f"💰 Total: <b>${venta.total:.2f}</b>\n"
                f"👤 Solicitado por: {cajero}\n\n"
                f"⏳ El enlace expira en 30 minutos."
            ),
            'parse_mode': 'HTML',
            'reply_markup': {
                'inline_keyboard': [[
                    {'text': '🔑 Autorizar cancelación', 'url': url_auth}
                ]]
            }
        })
        if result.get('ok'):
            return JsonResponse({'ok': True})
        return JsonResponse({'ok': False, 'error': 'No se pudo enviar a Telegram.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


def autorizar_cancelacion_view(request, token):
    """Página móvil donde el gerente ingresa su contraseña para autorizar la cancelación."""
    from django.contrib.auth import authenticate

    sol = get_object_or_404(SolicitudCancelacion, token=token)

    ctx = {'sol': sol, 'venta': sol.venta, 'error_form': None, 'link_invalido': None, 'exito': False}

    if sol.usado:
        ctx['link_invalido'] = 'Esta solicitud ya fue procesada.'
        return render(request, 'pos/autorizar_cancelacion.html', ctx)

    if sol.expirado():
        ctx['link_invalido'] = 'Este enlace expiró (30 min). El cajero debe solicitar uno nuevo.'
        return render(request, 'pos/autorizar_cancelacion.html', ctx)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user_auth = authenticate(request, username=username, password=password)

        es_supervisor = False
        if user_auth:
            if user_auth.is_superuser or getattr(user_auth, 'rol', '') == 'admin':
                es_supervisor = True
            elif UsuarioSucursal.objects.filter(
                usuario=user_auth, sucursal=sol.venta.sucursal,
                activo=True, rol='gerente'
            ).exists():
                es_supervisor = True

        if not es_supervisor:
            ctx['error_form'] = 'Credenciales incorrectas o sin permisos de supervisor.'
            return render(request, 'pos/autorizar_cancelacion.html', ctx)

        # Cancelar la venta y restaurar inventario
        with transaction.atomic():
            for det in sol.venta.detalles.select_related('producto').all():
                inv = Inventario.objects.filter(
                    producto=det.producto, sucursal=sol.venta.sucursal
                ).first()
                if inv:
                    stock_antes = inv.stock_actual
                    inv.stock_actual += det.cantidad
                    inv.save(update_fields=['stock_actual'])
                    MovimientoInventario.objects.create(
                        inventario=inv, tipo='entrada',
                        cantidad=det.cantidad,
                        stock_antes=stock_antes,
                        stock_despues=inv.stock_actual,
                        notas=f'Cancelación {sol.venta.folio} autorizada por {user_auth.get_full_name() or user_auth.username}',
                    )
            sol.venta.estado = 'cancelada'
            sol.venta.save(update_fields=['estado'])
            sol.usado = True
            sol.save(update_fields=['usado'])

        # Notificar en Telegram
        try:
            from produccion.telegram import enviar_async
            enviar_async(
                f"✅ <b>Cancelación autorizada</b>\n\n"
                f"🧾 Folio: <b>{sol.venta.folio}</b>\n"
                f"🏪 {sol.venta.sucursal.nombre}\n"
                f"💰 ${sol.venta.total:.2f}\n"
                f"🔑 Autorizado por: {user_auth.get_full_name() or user_auth.username}"
            )
        except Exception:
            pass

        ctx['exito'] = True
        return render(request, 'pos/autorizar_cancelacion.html', ctx)

    return render(request, 'pos/autorizar_cancelacion.html', ctx)
