from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Producto, Categoria, MensajeContacto, ConfiguracionSitio
from .forms import ContactoForm


def home(request):
    config = ConfiguracionSitio.get()
    productos_portada = Producto.objects.filter(mostrar_en_portada=True, disponible=True)[:8]
    context = {
        'config': config,
        'productos_portada': productos_portada,
    }
    return render(request, 'index.html', context)


def productos_view(request):
    categorias_reventa = Categoria.objects.filter(tipo='reventa')
    categorias_fabricado = Categoria.objects.filter(tipo='fabricado')
    categoria_id = request.GET.get('cat')
    tipo_filtro = request.GET.get('tipo', 'todos')

    productos = Producto.objects.filter(disponible=True)
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)
    if tipo_filtro in ('reventa', 'fabricado'):
        productos = productos.filter(categoria__tipo=tipo_filtro)

    context = {
        'productos': productos,
        'categorias_reventa': categorias_reventa,
        'categorias_fabricado': categorias_fabricado,
        'tipo_filtro': tipo_filtro,
        'categoria_id': categoria_id,
    }
    return render(request, 'productos.html', context)


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
