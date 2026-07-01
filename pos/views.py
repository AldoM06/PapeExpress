import json
import logging
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
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
    CategoriaPOS, UsuarioSucursal,
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

    prods = ProductoPOS.objects.filter(activo=True).select_related('categoria')
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
            'id':           p.id,
            'codigo':       p.codigo,
            'nombre':       p.nombre,
            'unidad':       p.unidad,
            'imagen':       p.imagen.url if p.imagen else None,
            'precio_1':     float(precio_obj.precio_1)      if precio_obj else 0,
            'precio_2':     float(precio_obj.precio_2)      if precio_obj and precio_obj.precio_2 else None,
            'precio_3':     float(precio_obj.precio_3)      if precio_obj and precio_obj.precio_3 else None,
            'en_oferta':    precio_obj.en_oferta            if precio_obj else False,
            'precio_oferta':float(precio_obj.precio_oferta) if precio_obj and precio_obj.precio_oferta else None,
            'stock':        float(inv.stock_actual)         if inv else 0,
            'costo':        float(inv.costo_promedio)       if inv else 0,
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

    # Productos críticos — filtro en SQL, no en Python
    criticos = Inventario.objects.select_related('producto', 'sucursal').filter(
        stock_actual__lte=F('stock_minimo'), stock_minimo__gt=0,
        sucursal__activa=True,
    ).order_by('sucursal__nombre', 'producto__nombre')

    return render(request, 'pos/dashboard_admin.html', {
        'reportes':    reportes,
        'total_mes':   total_mes,
        'ganancia_mes': ganancia_mes,
        'reinversion': reinversion,
        'criticos':    criticos[:20],
        'hoy':         hoy,
        'inicio_mes':  inicio_mes,
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

        return redirect('entrada_mercancia' + (f'?sucursal={sucursal.id}' if sucursal else ''))

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
    suc_activa = int(sucursal_sel_id) if sucursal_sel_id else (datos[0]['sucursal'].id if datos else None)

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
