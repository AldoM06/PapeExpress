from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Producto, Categoria, MensajeContacto, ConfiguracionSitio, FotoProducto
from .forms import ContactoForm


def _visibilidades_permitidas(user):
    """Retorna la lista de valores de visibilidad que el usuario puede ver."""
    permitidas = ['publico']
    if user.is_authenticated:
        rol = getattr(user, 'rol', '')
        if rol == 'cliente' and getattr(user, 'verificado', False):
            permitidas.append('clientes')
        if rol == 'socio':
            permitidas += ['clientes', 'socios']
        if user.is_staff or user.is_superuser:
            permitidas += ['clientes', 'socios']
    return permitidas


def _precio_visible(request, producto):
    """
    Retorna (precio_mostrar, es_mayoreo).
    - Cliente verificado → precio_mayoreo (si existe).
    - Todos los demás  → precio menudeo.
    """
    user = request.user
    es_cliente_verificado = (
        user.is_authenticated
        and getattr(user, 'verificado', False)
        and getattr(user, 'rol', '') == 'cliente'
    )
    if es_cliente_verificado and producto.precio_mayoreo:
        return producto.precio_mayoreo, True
    return producto.precio, False


def home(request):
    config = ConfiguracionSitio.get()
    permitidas = _visibilidades_permitidas(request.user)
    productos_portada = Producto.objects.filter(mostrar_en_portada=True, disponible=True, visibilidad__in=permitidas)[:8]
    return render(request, 'index.html', {
        'config': config,
        'productos_portada': productos_portada,
    })


def productos_view(request):
    categorias_reventa  = Categoria.objects.filter(tipo='reventa')
    categorias_fabricado = Categoria.objects.filter(tipo='fabricado')
    categoria_id = request.GET.get('cat')
    tipo_filtro  = request.GET.get('tipo', 'todos')

    user = request.user
    permitidas = _visibilidades_permitidas(user)
    productos = Producto.objects.filter(disponible=True, visibilidad__in=permitidas).select_related('categoria')
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)
    if tipo_filtro in ('reventa', 'fabricado'):
        productos = productos.filter(categoria__tipo=tipo_filtro)

    # Precio visible según rol
    es_mayoreo = (
        user.is_authenticated
        and getattr(user, 'verificado', False)
        and getattr(user, 'rol', '') == 'cliente'
    )

    return render(request, 'productos.html', {
        'productos':           productos,
        'categorias_reventa':  categorias_reventa,
        'categorias_fabricado': categorias_fabricado,
        'tipo_filtro':         tipo_filtro,
        'categoria_id':        categoria_id,
        'es_mayoreo':          es_mayoreo,
    })


def producto_detalle(request, pk):
    permitidas = _visibilidades_permitidas(request.user)
    producto   = get_object_or_404(Producto, pk=pk, disponible=True, visibilidad__in=permitidas)
    fotos      = producto.fotos.all()
    relacionados = Producto.objects.filter(
        categoria=producto.categoria, disponible=True, visibilidad__in=permitidas
    ).exclude(pk=pk)[:4]

    precio, es_mayoreo = _precio_visible(request, producto)

    return render(request, 'producto_detalle.html', {
        'producto':     producto,
        'fotos':        fotos,
        'relacionados': relacionados,
        'precio':       precio,
        'es_mayoreo':   es_mayoreo,
    })


def nosotros_view(request):
    config = ConfiguracionSitio.get()
    return render(request, 'nosotros.html', {'config': config})


def contacto_view(request):
    form = ContactoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '¡Mensaje enviado! Te contactaremos pronto.')
        return redirect('contacto')
    return render(request, 'contacto.html', {'form': form})


@staff_member_required
def presentacion_socios(request):
    return render(request, "presentacion_socios.html")

