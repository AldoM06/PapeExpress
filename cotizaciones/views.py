import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Producto
from produccion.telegram import (
    editar_mensaje_callback,
    notificar_nueva_cotizacion,
    notificar_verificacion_pendiente,
    responder_callback,
)

from .models import Cotizacion, DetalleCotizacion, TarifaEnvio


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_carrito(request):
    return request.session.get('carrito', {})


def _save_carrito(request, carrito):
    request.session['carrito'] = carrito
    request.session.modified = True


def _carrito_items(carrito):
    """Devuelve lista de (Producto, cantidad) para los ids del carrito."""
    if not carrito:
        return []
    productos = Producto.objects.filter(id__in=carrito.keys(), disponible=True).select_related('categoria')
    return [(p, int(carrito[str(p.id)])) for p in productos]


def _cliente_verificado(usuario):
    """
    Retorna True si el cliente puede enviar cotizaciones:
    - Ya fue marcado como verificado, o
    - Sus cotizaciones completadas suman >= $2,000.
    Si pasa por monto, actualiza el flag automáticamente.
    """
    if usuario.verificado:
        return True
    total_historico = sum(
        c.total_estimado
        for c in usuario.cotizaciones.filter(estado='completada')
    )
    if total_historico >= Decimal('2000'):
        usuario.verificado = True
        usuario.save(update_fields=['verificado'])
        return True
    return False


# ── Carrito ──────────────────────────────────────────────────────────────────

@login_required
def carrito_view(request):
    carrito = _get_carrito(request)
    items = _carrito_items(carrito)

    peso_total     = sum(p.peso * cant for p, cant in items)
    subtotal       = sum((p.precio or Decimal('0')) * cant for p, cant in items)
    cantidad_total = sum(cant for _, cant in items)
    tarifa         = TarifaEnvio.get()
    usuario        = request.user
    # Tarifa preferencial: precio fijo sin importar el peso
    if usuario.precio_envio_especial is not None:
        costo_envio_pe   = usuario.precio_envio_especial
        tarifa_especial  = True
    else:
        costo_envio_pe   = tarifa.calcular(peso_total)
        tarifa_especial  = False

    return render(request, 'cotizaciones/carrito.html', {
        'items':          items,
        'peso_total':     peso_total,
        'subtotal':       subtotal,
        'cantidad_total': cantidad_total,
        'verificado':     _cliente_verificado(usuario) if items else None,
        'tarifa':         tarifa,
        'costo_envio_pe': costo_envio_pe,
        'tarifa_especial': tarifa_especial,
        # Dirección guardada en el perfil para autocompletar
        'dir_default': {
            'calle':   usuario.dir_calle,
            'colonia': usuario.dir_colonia,
            'ciudad':  usuario.dir_ciudad,
            'estado':  usuario.dir_estado,
            'cp':      usuario.dir_cp,
        },
    })


@login_required
def agregar_producto(request, producto_id):
    if request.method != 'POST':
        return redirect('carrito')

    producto = get_object_or_404(Producto, id=producto_id, disponible=True)
    try:
        cantidad = max(1, int(request.POST.get('cantidad', 1)))
    except (ValueError, TypeError):
        cantidad = 1

    carrito = _get_carrito(request)
    key = str(producto_id)
    carrito[key] = carrito.get(key, 0) + cantidad
    _save_carrito(request, carrito)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        total_items = sum(carrito.values())
        return JsonResponse({'ok': True, 'total_items': total_items})

    messages.success(request, f'"{producto.nombre}" agregado al carrito.')
    return redirect(request.POST.get('next', 'productos'))


@login_required
def quitar_producto(request, producto_id):
    carrito = _get_carrito(request)
    carrito.pop(str(producto_id), None)
    _save_carrito(request, carrito)
    return redirect('carrito')


@login_required
def actualizar_cantidad(request, producto_id):
    if request.method != 'POST':
        return redirect('carrito')
    carrito = _get_carrito(request)
    key = str(producto_id)
    try:
        cantidad = int(request.POST.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad = 1

    if cantidad <= 0:
        carrito.pop(key, None)
    else:
        carrito[key] = cantidad
    _save_carrito(request, carrito)
    return redirect('carrito')


# ── Verificación ─────────────────────────────────────────────────────────────

@login_required
def subir_verificacion(request):
    if request.method == 'POST':
        foto = request.FILES.get('foto_negocio')
        if not foto:
            messages.error(request, 'Por favor selecciona una imagen de tu negocio.')
            return render(request, 'cotizaciones/verificacion.html')

        request.user.foto_negocio = foto
        request.user.save(update_fields=['foto_negocio'])

        # Notifica al grupo de Telegram con botones Aprobar/Rechazar
        notificar_verificacion_pendiente(request.user)

        messages.success(
            request,
            'Foto enviada correctamente. Te avisaremos cuando sea aprobada.'
        )
        return redirect('carrito')

    return render(request, 'cotizaciones/verificacion.html')


@login_required
def estado_verificacion(request):
    """Endpoint liviano para que la página de espera consulte si ya fue aprobado."""
    return JsonResponse({'verificado': request.user.verificado})


# ── Enviar cotización ─────────────────────────────────────────────────────────

@login_required
def enviar_cotizacion(request):
    if request.method != 'POST':
        return redirect('carrito')

    carrito = _get_carrito(request)
    items = _carrito_items(carrito)

    if not items:
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('carrito')

    if not _cliente_verificado(request.user):
        messages.warning(
            request,
            'Para enviar una cotización necesitamos verificar tu negocio. '
            'Sube una foto de tu papelería o tienda.'
        )
        return redirect('subir_verificacion')

    notas          = request.POST.get('notas', '').strip()
    metodo_envio   = request.POST.get('metodo_envio', 'papeexpress')
    dir_calle      = request.POST.get('dir_calle', '').strip()
    dir_colonia    = request.POST.get('dir_colonia', '').strip()
    dir_ciudad     = request.POST.get('dir_ciudad', '').strip()
    dir_estado     = request.POST.get('dir_estado', '').strip()
    dir_cp         = request.POST.get('dir_cp', '').strip()
    fecha_req      = request.POST.get('fecha_requerida') or None
    notas_entrega  = request.POST.get('notas_entrega', '').strip()
    guardar_dir    = request.POST.get('guardar_direccion') == '1'

    with transaction.atomic():
        peso_total = Decimal('0')
        total_estimado = Decimal('0')

        cotizacion = Cotizacion.objects.create(
            cliente=request.user,
            notas=notas,
            metodo_envio=metodo_envio,
            direccion_calle=dir_calle,
            direccion_colonia=dir_colonia,
            direccion_ciudad=dir_ciudad,
            direccion_estado=dir_estado,
            direccion_cp=dir_cp,
            fecha_requerida=fecha_req,
            notas_entrega=notas_entrega,
        )

        for producto, cantidad in items:
            precio = producto.precio or Decimal('0')
            subtotal = precio * cantidad
            peso_producto = producto.peso * cantidad
            total_estimado += subtotal
            peso_total += peso_producto

            DetalleCotizacion.objects.create(
                cotizacion=cotizacion,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
            )

        # Calcular costo de envío (tarifa especial tiene prioridad)
        costo_envio = Decimal('0')
        if metodo_envio == 'papeexpress':
            if request.user.precio_envio_especial is not None:
                costo_envio = request.user.precio_envio_especial
            else:
                costo_envio = TarifaEnvio.get().calcular(peso_total)

        cotizacion.peso_total     = peso_total
        cotizacion.total_estimado = total_estimado
        cotizacion.costo_envio    = costo_envio
        cotizacion.save(update_fields=['peso_total', 'total_estimado', 'costo_envio'])

        # Guardar dirección en el perfil si el cliente lo pidió
        if guardar_dir and metodo_envio != 'recoger':
            request.user.dir_calle   = dir_calle
            request.user.dir_colonia = dir_colonia
            request.user.dir_ciudad  = dir_ciudad
            request.user.dir_estado  = dir_estado
            request.user.dir_cp      = dir_cp
            request.user.save(update_fields=['dir_calle','dir_colonia','dir_ciudad','dir_estado','dir_cp'])

    # Limpiar carrito
    _save_carrito(request, {})

    # Alerta Telegram
    notificar_nueva_cotizacion(cotizacion)

    messages.success(
        request,
        f'¡Cotización #{cotizacion.id} enviada! Te contactaremos pronto.'
    )
    return redirect('historial_cotizaciones')


# ── Historial ─────────────────────────────────────────────────────────────────

@login_required
def historial_view(request):
    cotizaciones = request.user.cotizaciones.prefetch_related('detalles__producto')
    return render(request, 'cotizaciones/historial.html', {'cotizaciones': cotizaciones})


# ── Webhook Telegram ──────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def telegram_webhook(request):
    """
    Recibe callbacks de Telegram cuando el admin presiona Aprobar/Rechazar
    en el mensaje de verificación de negocio.
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model

    # Verificar token secreto en la URL para seguridad
    token_param = request.GET.get('token', '')
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token or token_param != bot_token[-10:]:
        return JsonResponse({'ok': False}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False}, status=400)

    callback = data.get('callback_query')
    if not callback:
        return JsonResponse({'ok': True})

    callback_id = callback['id']
    callback_data = callback.get('data', '')
    message = callback.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ''))
    message_id = message.get('message_id')

    Usuario = get_user_model()

    if callback_data.startswith('verif_aprobar_'):
        user_id = int(callback_data.replace('verif_aprobar_', ''))
        try:
            usuario = Usuario.objects.get(pk=user_id)
            usuario.verificado = True
            usuario.save(update_fields=['verificado'])
            nombre = usuario.get_full_name() or usuario.username
            responder_callback(callback_id, f'✅ {nombre} aprobado como cliente verificado.')
            editar_mensaje_callback(
                chat_id, message_id,
                f"✅ <b>APROBADO</b>\n\n"
                f"👤 {nombre} ya puede enviar cotizaciones.\n"
                f"📞 {usuario.telefono or 'Sin tel'} | 📧 {usuario.email}"
            )
        except Usuario.DoesNotExist:
            responder_callback(callback_id, 'Usuario no encontrado.')

    elif callback_data.startswith('verif_rechazar_'):
        user_id = int(callback_data.replace('verif_rechazar_', ''))
        try:
            usuario = Usuario.objects.get(pk=user_id)
            # Quitar la foto para que pueda intentarlo de nuevo
            usuario.foto_negocio.delete(save=False)
            usuario.foto_negocio = None
            usuario.verificado = False
            usuario.save(update_fields=['foto_negocio', 'verificado'])
            nombre = usuario.get_full_name() or usuario.username
            responder_callback(callback_id, f'❌ {nombre} rechazado.')
            editar_mensaje_callback(
                chat_id, message_id,
                f"❌ <b>RECHAZADO</b>\n\n"
                f"👤 {nombre} fue notificado para subir una nueva foto.\n"
                f"📞 {usuario.telefono or 'Sin tel'} | 📧 {usuario.email}"
            )
        except Usuario.DoesNotExist:
            responder_callback(callback_id, 'Usuario no encontrado.')

    return JsonResponse({'ok': True})
