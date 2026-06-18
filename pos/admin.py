from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ClientePOS, Sucursal, UsuarioSucursal, CategoriaPOS,
    ProductoPOS, PrecioPorSucursal, Inventario, MovimientoInventario,
    Venta, DetalleVenta, Abono, Anticipo,
    Proveedor, CompraProveedor, DetalleCompra, PrecioHistoricoProveedor,
)


# ── CLIENTES / SUCURSALES ─────────────────────────────────
class SucursalInline(admin.TabularInline):
    model  = Sucursal
    extra  = 1
    fields = ('nombre', 'tipo', 'activa')


@admin.register(ClientePOS)
class ClientePOSAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rfc', 'telefono', 'activo')
    inlines      = [SucursalInline]


class UsuarioSucursalInline(admin.TabularInline):
    model  = UsuarioSucursal
    extra  = 1
    fields = ('usuario', 'rol', 'activo')


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'cliente', 'tipo', 'activa')
    list_filter   = ('tipo', 'activa', 'cliente')
    inlines       = [UsuarioSucursalInline]


# ── PRODUCTOS ─────────────────────────────────────────────
class PrecioInline(admin.TabularInline):
    model  = PrecioPorSucursal
    extra  = 1
    fields = ('sucursal', 'precio_1', 'precio_2', 'precio_3', 'en_oferta', 'precio_oferta', 'activo')


@admin.register(ProductoPOS)
class ProductoPOSAdmin(admin.ModelAdmin):
    list_display  = ('codigo', 'nombre', 'categoria', 'unidad', 'activo')
    list_filter   = ('categoria', 'activo')
    list_editable = ('activo',)
    search_fields = ('nombre', 'codigo')
    inlines       = [PrecioInline]


@admin.register(CategoriaPOS)
class CategoriaPOSAdmin(admin.ModelAdmin):
    list_display = ('icono', 'nombre', 'color')


# ── INVENTARIO ────────────────────────────────────────────
@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display  = ('producto', 'sucursal', 'stock_actual', 'stock_minimo',
                     'costo_promedio', 'alerta_display')
    list_filter   = ('sucursal',)
    list_editable = ('stock_minimo',)
    search_fields = ('producto__nombre', 'producto__codigo')

    def alerta_display(self, obj):
        if obj.bajo_minimo:
            return format_html('<span style="color:red;font-weight:700">⚠️ BAJO MÍNIMO</span>')
        return '✅'
    alerta_display.short_description = 'Estado'


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('inventario', 'tipo', 'cantidad', 'stock_antes', 'stock_despues', 'fecha')
    list_filter  = ('tipo', 'fecha')
    readonly_fields = ('fecha',)


# ── VENTAS ────────────────────────────────────────────────
class DetalleVentaInline(admin.TabularInline):
    model       = DetalleVenta
    extra       = 0
    readonly_fields = ('subtotal',)


class AbonoInline(admin.TabularInline):
    model  = Abono
    extra  = 0
    readonly_fields = ('fecha',)


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display  = ('folio', 'sucursal', 'cajero', 'total', 'forma_pago',
                     'estado', 'saldo_pendiente', 'creado')
    list_filter   = ('estado', 'forma_pago', 'sucursal', 'creado')
    search_fields = ('folio',)
    readonly_fields = ('folio', 'ganancia_display', 'creado')
    inlines       = [DetalleVentaInline, AbonoInline]

    def ganancia_display(self, obj):
        return f'${obj.ganancia:.2f}'
    ganancia_display.short_description = 'Ganancia'


@admin.register(Anticipo)
class AnticipoAdmin(admin.ModelAdmin):
    list_display = ('cliente_nombre', 'sucursal', 'total_pedido',
                    'anticipo_pagado', 'saldo', 'entregado', 'fecha_prometida')
    list_filter  = ('entregado', 'sucursal')
    list_editable = ('entregado',)


# ── PROVEEDORES ───────────────────────────────────────────
class DetalleCompraInline(admin.TabularInline):
    model  = DetalleCompra
    extra  = 1
    fields = ('producto', 'cantidad', 'costo_unitario', 'subtotal')
    readonly_fields = ('subtotal',)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'rfc', 'telefono', 'email', 'activo')
    list_editable = ('activo',)
    search_fields = ('nombre', 'rfc')


@admin.register(CompraProveedor)
class CompraProveedorAdmin(admin.ModelAdmin):
    list_display  = ('folio', 'proveedor', 'sucursal', 'total', 'estado', 'fecha_compra')
    list_filter   = ('estado', 'sucursal', 'proveedor')
    search_fields = ('folio', 'proveedor__nombre')
    readonly_fields = ('analisis_ocr', 'creado')
    inlines       = [DetalleCompraInline]


@admin.register(PrecioHistoricoProveedor)
class PrecioHistoricoAdmin(admin.ModelAdmin):
    list_display = ('proveedor', 'producto', 'costo', 'fecha')
    list_filter  = ('proveedor', 'fecha')
