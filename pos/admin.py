from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ClientePOS, Sucursal, UsuarioSucursal, CategoriaPOS,
    ProductoPOS, PrecioPorSucursal, Inventario, MovimientoInventario,
    Venta, DetalleVenta, Abono, Anticipo,
    Proveedor, CompraProveedor, DetalleCompra, PrecioHistoricoProveedor,
    ConfigPOS, GastoFijo, TransaccionServicio, CierreCaja,
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


class GastoFijoInline(admin.TabularInline):
    model   = GastoFijo
    extra   = 1
    fields  = ('tipo', 'descripcion', 'monto', 'activo')


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'cliente', 'tipo', 'telefono', 'whatsapp', 'activa')
    list_filter   = ('tipo', 'activa', 'cliente')
    fields        = ('cliente', 'nombre', 'tipo', 'logo', 'direccion', 'telefono', 'whatsapp', 'activa')
    inlines       = [UsuarioSucursalInline, GastoFijoInline]


@admin.register(GastoFijo)
class GastoFijoAdmin(admin.ModelAdmin):
    list_display  = ('sucursal', 'tipo', 'descripcion', 'monto', 'activo')
    list_filter   = ('sucursal', 'tipo', 'activo')
    list_editable = ('monto', 'activo')


# ── PRODUCTOS ─────────────────────────────────────────────
class PrecioInline(admin.TabularInline):
    model  = PrecioPorSucursal
    extra  = 1
    fields = ('sucursal', 'precio_1', 'precio_2', 'precio_3', 'en_oferta', 'precio_oferta', 'activo')


@admin.register(ProductoPOS)
class ProductoPOSAdmin(admin.ModelAdmin):
    list_display  = ('codigo', 'nombre', 'categoria', 'unidad', 'favorito_pos', 'activo')
    list_filter   = ('categoria', 'activo', 'favorito_pos')
    list_editable = ('activo', 'favorito_pos')
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


# ── RECARGAS Y SERVICIOS ──────────────────────────────────
@admin.register(TransaccionServicio)
class TransaccionServicioAdmin(admin.ModelAdmin):
    list_display  = ('fecha', 'sucursal', 'cajero', 'tipo', 'servicio', 'telefono', 'monto', 'comision', 'referencia')
    list_filter   = ('tipo', 'servicio', 'sucursal', 'fecha')
    search_fields = ('telefono', 'referencia', 'cajero__username')
    readonly_fields = ('fecha',)
    date_hierarchy = 'fecha'


@admin.register(CierreCaja)
class CierreCajaAdmin(admin.ModelAdmin):
    list_display  = ('fecha', 'sucursal', 'estado', 'cambio_inicial', 'total_ventas_efectivo',
                     'total_retiros', 'efectivo_esperado', 'efectivo_contado', 'diferencia')
    list_filter   = ('estado', 'sucursal', 'fecha')
    readonly_fields = ('apertura_en', 'cierre_en')
    date_hierarchy = 'fecha'


# ── CONFIGURACIÓN POS ─────────────────────────────────────
@admin.register(ConfigPOS)
class ConfigPOSAdmin(admin.ModelAdmin):
    fields = ('pct_reinversion', 'whatsapp_general')

    def has_add_permission(self, request):
        return not ConfigPOS.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
