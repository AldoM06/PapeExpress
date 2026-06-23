import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings
from django.utils import timezone

from .models import SocioComercial, PedidoFomy
from produccion.models import FiguraFomy
from produccion.telegram import notificar_nuevo_pedido, notificar_pago_confirmado

logger = logging.getLogger(__name__)


def mapa_socios(request):
    socios = SocioComercial.objects.filter(activo=True, mostrar_en_mapa=True).order_by('-destacado','nombre')
    socios_json = json.dumps([
        {
            'id':           s.id,
            'nombre':       s.nombre,
            'tipo_negocio': s.tipo_negocio,
            'slogan':       s.slogan,
            'descripcion':  s.descripcion,
            'direccion':    s.direccion,
            'ciudad':       s.ciudad,
            'estado':       s.estado,
            'telefono':     s.telefono,
            'whatsapp_1':   s.whatsapp_1_url,
            'whatsapp_2':   s.whatsapp_2_url,
            'facebook':     s.facebook_url,
            'instagram':    s.instagram_url,
            'horario':      s.horario,
            'destacado':    s.destacado,
            'logo':         s.logo.url if s.logo else '',
            'foto':         s.foto_negocio.url if s.foto_negocio else '',
            'lat':          s.latitud,
            'lng':          s.longitud,
            'maps_url':     s.maps_url,
        }
        for s in socios if s.latitud and s.longitud
    ])
    return render(request, 'socios/mapa.html', {
        'socios_json': socios_json,
        'socios':      socios,
        'destacados':  socios.filter(destacado=True),
    })


def socios_api(request):
    socios = SocioComercial.objects.filter(activo=True, mostrar_en_mapa=True)
    return JsonResponse({'socios': [
        {'id': s.id, 'nombre': s.nombre, 'lat': s.latitud, 'lng': s.longitud}
        for s in socios if s.latitud and s.longitud
    ]})


@login_required
def portal_socio(request):
    try:
        socio = request.user.perfil_socio
    except Exception:
        messages.error(request, 'No tienes perfil de socio. Contacta a PaPeExpress.')
        return redirect('home')
    figuras     = FiguraFomy.objects.filter(cantidad_disponible__gt=0).order_by('nombre')
    mis_pedidos = PedidoFomy.objects.filter(socio=socio).select_related('figura').order_by('-creado')[:20]
    return render(request, 'socios/portal.html', {
        'socio':       socio,
        'figuras':     figuras,
        'mis_pedidos': mis_pedidos,
        'stripe_pk':   getattr(settings, 'STRIPE_PUBLIC_KEY', ''),
    })


@login_required
@require_POST
def crear_pedido(request):
    try:
        socio = request.user.perfil_socio
    except Exception:
        return JsonResponse({'error': 'Sin perfil de socio'}, status=403)

    from decimal import Decimal
    figura_id = request.POST.get('figura_id')
    cantidad  = int(request.POST.get('cantidad', 1))
    figura    = get_object_or_404(FiguraFomy, pk=figura_id)

    if cantidad > figura.cantidad_disponible:
        messages.error(request, f'Solo hay {figura.cantidad_disponible} piezas disponibles.')
        return redirect('portal_socio')
    if not figura.precio_venta:
        messages.error(request, 'Esta figura no tiene precio de venta.')
        return redirect('portal_socio')

    pedido = PedidoFomy.objects.create(
        socio=socio, figura=figura, cantidad=cantidad,
        precio_unitario=figura.precio_venta, estado='pendiente',
    )
    notificar_nuevo_pedido(pedido)

    stripe_secret = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if stripe_secret:
        try:
            import stripe
            stripe.api_key = stripe_secret
            domain = request.build_absolute_uri('/').rstrip('/')
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{'price_data': {
                    'currency': 'mxn',
                    'product_data': {'name': f'{figura.nombre} x{cantidad}'},
                    'unit_amount': int(figura.precio_venta * 100),
                }, 'quantity': cantidad}],
                mode='payment',
                success_url=f'{domain}/socios/pedido/{pedido.pk}/exito/?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=f'{domain}/socios/pedido/{pedido.pk}/cancelado/',
                metadata={'pedido_id': pedido.pk},
            )
            pedido.stripe_session_id = session.id
            pedido.save()
            return redirect(session.url, code=303)
        except Exception as e:
            logger.error(f'Stripe error: {e}')
            messages.warning(request, 'Error con la pasarela de pago. Pedido registrado.')
            return redirect('portal_socio')
    else:
        messages.success(request, 'Pedido registrado. PaPeExpress te contactará.')
        return redirect('portal_socio')


@login_required
def pedido_exitoso(request, pk):
    pedido = get_object_or_404(PedidoFomy, pk=pk)
    session_id = request.GET.get('session_id', '')
    if pedido.estado == 'pendiente':
        stripe_secret = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if stripe_secret and session_id:
            try:
                import stripe
                stripe.api_key = stripe_secret
                session = stripe.checkout.Session.retrieve(session_id)
                if session.payment_status == 'paid':
                    pedido.estado = 'pagado'
                    pedido.stripe_payment_intent = session.payment_intent or ''
                    pedido.pagado_en = timezone.now()
                    pedido.save()
                    figura = pedido.figura
                    figura.cantidad_disponible = max(0, figura.cantidad_disponible - pedido.cantidad)
                    figura.save()
                    notificar_pago_confirmado(pedido)
            except Exception as e:
                logger.error(f'Stripe verify: {e}')
        else:
            pedido.estado = 'pagado'
            pedido.pagado_en = timezone.now()
            pedido.save()
    return render(request, 'socios/pedido_exitoso.html', {'pedido': pedido})


@login_required
def pedido_cancelado(request, pk):
    pedido = get_object_or_404(PedidoFomy, pk=pk)
    if pedido.estado == 'pendiente':
        pedido.estado = 'cancelado'
        pedido.save()
    messages.warning(request, 'Pago cancelado. Pedido pendiente.')
    return redirect('portal_socio')


@csrf_exempt
def stripe_webhook(request):
    stripe_secret  = getattr(settings, 'STRIPE_SECRET_KEY', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    if not stripe_secret or not webhook_secret:
        logger.error('Webhook recibido sin Stripe configurado — rechazado')
        return HttpResponse(status=400)
    try:
        import stripe
        stripe.api_key = stripe_secret
        event = stripe.Webhook.construct_event(
            request.body, request.META.get('HTTP_STRIPE_SIGNATURE', ''), webhook_secret
        )
    except Exception as e:
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session   = event['data']['object']
        pedido_id = session.get('metadata', {}).get('pedido_id')
        if pedido_id:
            try:
                pedido = PedidoFomy.objects.get(pk=pedido_id)
                if pedido.estado == 'pendiente':
                    pedido.estado = 'pagado'
                    pedido.stripe_payment_intent = session.get('payment_intent', '')
                    pedido.pagado_en = timezone.now()
                    pedido.save()
                    figura = pedido.figura
                    figura.cantidad_disponible = max(0, figura.cantidad_disponible - pedido.cantidad)
                    figura.save()
                    notificar_pago_confirmado(pedido)
            except PedidoFomy.DoesNotExist:
                pass
    return HttpResponse(status=200)
