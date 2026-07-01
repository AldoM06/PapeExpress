from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Producto, Categoria, MensajeContacto, ConfiguracionSitio, FotoProducto
from .forms import ContactoForm


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
    productos_portada = Producto.objects.filter(mostrar_en_portada=True, disponible=True)[:8]
    return render(request, 'index.html', {
        'config': config,
        'productos_portada': productos_portada,
    })


def productos_view(request):
    categorias_reventa  = Categoria.objects.filter(tipo='reventa')
    categorias_fabricado = Categoria.objects.filter(tipo='fabricado')
    categoria_id = request.GET.get('cat')
    tipo_filtro  = request.GET.get('tipo', 'todos')

    productos = Producto.objects.filter(disponible=True).select_related('categoria')
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)
    if tipo_filtro in ('reventa', 'fabricado'):
        productos = productos.filter(categoria__tipo=tipo_filtro)

    # Precio visible según rol
    user = request.user
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
    producto   = get_object_or_404(Producto, pk=pk, disponible=True)
    fotos      = producto.fotos.all()
    relacionados = Producto.objects.filter(
        categoria=producto.categoria, disponible=True
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
