from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import LoginForm, RegistroClienteForm


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
    context = {
        'total_productos': Producto.objects.count(),
        'total_figuras': FiguraFomy.objects.count(),
        'mensajes_nuevos': MensajeContacto.objects.filter(leido=False).count(),
    }
    return render(request, 'dashboard/admin.html', context)


@login_required
def dashboard_cliente(request):
    return render(request, 'dashboard/cliente.html')


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
def dashboard_produccion(request):
    from produccion.models import FiguraFomy
    figuras = FiguraFomy.objects.all()
    return render(request, 'dashboard/produccion.html', {'figuras': figuras})
