from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from .forms import LoginForm, RegistroClienteForm
from .models import Usuario


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


def registro_view(request):
    form = RegistroClienteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, '¡Bienvenido a PapeExpress!')
        return redirect('dashboard')
    return render(request, 'registration/registro.html', {'form': form})


@login_required
def dashboard_view(request):
    user = request.user
    rol = user.rol

    if rol == 'admin' or user.is_superuser:
        return redirect('dashboard_admin')
    elif rol == 'socio':
        return redirect('dashboard_socio')
    elif rol == 'ventas':
        return redirect('dashboard_ventas')
    elif rol == 'almacen':
        return redirect('dashboard_almacen')
    elif rol in ('diseño', 'produccion'):
        return redirect('dashboard_produccion')
    else:
        return redirect('dashboard_cliente')


@login_required
def dashboard_admin(request):
    if not (request.user.rol == 'admin' or request.user.is_superuser):
        return redirect('dashboard')
    from core.models import Producto, MensajeContacto
    from produccion.models import FiguraFomy
    from cotizaciones.models import Cotizacion
    context = {
        'total_productos':    Producto.objects.count(),
        'total_figuras':      FiguraFomy.objects.count(),
        'mensajes_nuevos':    MensajeContacto.objects.filter(leido=False).count(),
        'cotizaciones_pendientes': Cotizacion.objects.filter(estado='pendiente')
            .select_related('cliente')
            .prefetch_related('detalles__producto')
            .order_by('-creado'),
        'cotizaciones_procesando': Cotizacion.objects.filter(estado='procesando')
            .select_related('cliente')
            .prefetch_related('detalles__producto')
            .order_by('-creado'),
        'verificaciones_pendientes': Usuario.objects.filter(
            foto_negocio__isnull=False, verificado=False, rol='cliente'
        ).exclude(foto_negocio=''),
    }
    return render(request, 'dashboard/admin.html', context)


@login_required
def dashboard_cliente(request):
    from cotizaciones.models import Cotizacion
    cotizaciones = (
        request.user.cotizaciones
        .prefetch_related('detalles__producto')
        .order_by('-creado')
    )
    pendientes   = cotizaciones.filter(estado='pendiente')
    procesando   = cotizaciones.filter(estado='procesando')
    completadas  = cotizaciones.filter(estado='completada')
    recientes    = cotizaciones[:5]
    return render(request, 'dashboard/cliente.html', {
        'cotizaciones':  cotizaciones,
        'recientes':     recientes,
        'num_pendientes': pendientes.count(),
        'num_procesando': procesando.count(),
        'num_completadas': completadas.count(),
    })


@login_required
def dashboard_socio(request):
    if request.user.rol not in ('socio', 'admin') and not request.user.is_superuser:
        return redirect('dashboard')
    from produccion.models import FiguraFomy
    figuras = FiguraFomy.objects.all().order_by('-actualizado')
    return render(request, 'dashboard/socio.html', {'figuras': figuras})


@login_required
def dashboard_ventas(request):
    return render(request, 'dashboard/ventas.html')


@login_required
def dashboard_almacen(request):
    return render(request, 'dashboard/almacen.html')


@login_required
@require_POST
def gestionar_cotizacion(request, pk):
    """Admin confirma disponibilidad o pone fecha estimada en una cotización."""
    if not (request.user.rol == 'admin' or request.user.is_superuser):
        messages.error(request, 'Sin permisos.')
        return redirect('dashboard_admin')

    from cotizaciones.models import Cotizacion
    from produccion.telegram import enviar_async

    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    accion     = request.POST.get('accion')  # 'confirmar' | 'sin_stock'

    if accion == 'confirmar':
        cotizacion.estado = 'procesando'
        cotizacion.save(update_fields=['estado'])
        cliente = cotizacion.cliente
        nombre  = cliente.get_full_name() or cliente.username
        enviar_async(
            f"✅ <b>Cotización #{cotizacion.id} confirmada</b>\n"
            f"👤 {nombre} | 📞 {cliente.telefono or '—'}\n"
            f"Todos los productos están disponibles. En proceso de preparación."
        )
        messages.success(request, f'Cotización #{pk} marcada como En proceso.')

    elif accion == 'completar':
        cotizacion.estado = 'completada'
        cotizacion.save(update_fields=['estado'])
        cliente = cotizacion.cliente
        nombre  = cliente.get_full_name() or cliente.username
        enviar_async(
            f"🎉 <b>Cotización #{cotizacion.id} completada</b>\n"
            f"👤 {nombre} | 📞 {cliente.telefono or '—'}\n"
            f"El pedido ha sido entregado/cerrado."
        )
        messages.success(request, f'Cotización #{pk} marcada como Completada.')

    elif accion == 'sin_stock':
        fecha_estimada = request.POST.get('fecha_estimada', '').strip()
        notas_admin    = request.POST.get('notas_admin', '').strip()
        if fecha_estimada:
            cotizacion.fecha_requerida = fecha_estimada
        if notas_admin:
            cotizacion.notas = (cotizacion.notas + '\n\n[Admin] ' + notas_admin).strip()
        cotizacion.estado = 'procesando'
        cotizacion.save(update_fields=['estado', 'fecha_requerida', 'notas'])
        cliente = cotizacion.cliente
        nombre  = cliente.get_full_name() or cliente.username
        fecha_txt = fecha_estimada or 'por confirmar'
        enviar_async(
            f"⚠️ <b>Cotización #{cotizacion.id} — Stock parcial</b>\n"
            f"👤 {nombre} | 📞 {cliente.telefono or '—'}\n"
            f"📅 Fecha estimada de entrega: {fecha_txt}\n"
            f"📝 {notas_admin or 'Sin notas adicionales'}"
        )
        messages.warning(request, f'Cotización #{pk} actualizada con fecha estimada.')

    return redirect('dashboard_admin')


@login_required
def dashboard_produccion(request):
    from produccion.models import FiguraFomy
    figuras = FiguraFomy.objects.all()
    return render(request, 'dashboard/produccion.html', {'figuras': figuras})
