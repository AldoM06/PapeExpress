from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


# ══════════════════════════════════════════════════════════
#  CLIENTES / SUCURSALES
# ══════════════════════════════════════════════════════════

class ClientePOS(models.Model):
    """Empresa cliente que usa el POS (multi-tenant)."""
    nombre      = models.CharField(max_length=200)
    rfc         = models.CharField(max_length=20, blank=True)
    telefono    = models.CharField(max_length=20, blank=True)
    email       = models.EmailField(blank=True)
    activo      = models.BooleanField(default=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cliente POS'
        verbose_name_plural = 'Clientes POS'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Sucursal(models.Model):
    """Sucursal de un cliente. Ej: Hércules, Maury, Roshita."""
    TIPO_CHOICES = [
        ('mayoreo',  'Mayoreo'),
        ('menudeo',  'Menudeo'),
        ('mixto',    'Mayoreo y Menudeo'),
    ]
    cliente     = models.ForeignKey(ClientePOS, on_delete=models.CASCADE, related_name='sucursales')
    nombre      = models.CharField(max_length=200)
    tipo        = models.CharField(max_length=10, choices=TIPO_CHOICES, default='mixto')
    logo        = models.ImageField(upload_to='pos/sucursales/', blank=True, null=True,
                                    verbose_name='Logo de la sucursal')
    direccion   = models.TextField(blank=True)
    telefono    = models.CharField(max_length=20, blank=True)
    whatsapp    = models.CharField('WhatsApp', max_length=20, blank=True,
                                   help_text='Número sin espacios ni +52, ej: 5512345678')
    activa      = models.BooleanField(default=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sucursal'
        verbose_name_plural = 'Sucursales'
        ordering = ['cliente', 'nombre']

    def __str__(self):
        return f'{self.cliente.nombre} — {self.nombre}'


class UsuarioSucursal(models.Model):
    """Relación usuario ↔ sucursal con rol dentro del POS."""
    ROL_CHOICES = [
        ('cajero',    'Cajero'),
        ('vendedor',  'Vendedor'),
        ('gerente',   'Gerente de sucursal'),
        ('almacen',   'Encargado de almacén'),
    ]
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='sucursales_pos')
    sucursal    = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='usuarios')
    rol         = models.CharField(max_length=20, choices=ROL_CHOICES, default='cajero')
    activo      = models.BooleanField(default=True)

    class Meta:
        unique_together = ('usuario', 'sucursal')
        verbose_name = 'Usuario de Sucursal'
        verbose_name_plural = 'Usuarios de Sucursal'

    def __str__(self):
        return f'{self.usuario.username} → {self.sucursal.nombre} ({self.get_rol_display()})'


# ══════════════════════════════════════════════════════════
#  CATÁLOGO DE PRODUCTOS POS
# ══════════════════════════════════════════════════════════

class CategoriaPOS(models.Model):
    nombre      = models.CharField(max_length=100)
    icono       = models.CharField(max_length=10, blank=True, default='📦')
    color       = models.CharField(max_length=7, blank=True, default='#6c757d')

    class Meta:
        verbose_name = 'Categoría POS'
        verbose_name_plural = 'Categorías POS'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class ProductoPOS(models.Model):
    """Producto maestro compartido entre sucursales."""
    categoria   = models.ForeignKey(CategoriaPOS, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='productos')
    codigo      = models.CharField(max_length=50, unique=True, help_text='Código de barras o clave interna')
    nombre      = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    imagen      = models.ImageField(upload_to='pos/productos/', blank=True, null=True)
    unidad      = models.CharField(max_length=30, default='pieza',
                                   help_text='pieza, caja, kg, litro, etc.')
    peso        = models.DecimalField('Peso (kg)', max_digits=6, decimal_places=3, default=0,
                                      help_text='Peso por unidad en kg. Usado para calcular envíos.')
    activo      = models.BooleanField(default=True)
    favorito_pos = models.BooleanField(
        'Favorito del POS', default=False,
        help_text='Aparece en la pestaña "Favoritos" al abrir el POS.'
    )
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Producto POS'
        verbose_name_plural = 'Productos POS'
        ordering = ['nombre']

    def __str__(self):
        return f'[{self.codigo}] {self.nombre}'


class PrecioPorSucursal(models.Model):
    """3 niveles de precio por sucursal por producto."""
    producto    = models.ForeignKey(ProductoPOS, on_delete=models.CASCADE, related_name='precios')
    sucursal    = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='precios')
    precio_1    = models.DecimalField(max_digits=10, decimal_places=2, help_text='Precio menudeo')
    precio_2    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                      help_text='Precio mayoreo / 2do nivel')
    precio_3    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                      help_text='Precio especial / 3er nivel')
    precio_traspaso = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          help_text='Precio interno para traspasos entre sucursales (P4)')
    en_oferta   = models.BooleanField(default=False)
    precio_oferta = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    activo      = models.BooleanField(default=True)

    class Meta:
        unique_together = ('producto', 'sucursal')
        verbose_name = 'Precio por Sucursal'
        verbose_name_plural = 'Precios por Sucursal'

    def __str__(self):
        return f'{self.producto.nombre} @ {self.sucursal.nombre}'

    def get_precio(self, nivel=1):
        if self.en_oferta and self.precio_oferta:
            return self.precio_oferta
        return getattr(self, f'precio_{nivel}', self.precio_1) or self.precio_1


# ══════════════════════════════════════════════════════════
#  INVENTARIO
# ══════════════════════════════════════════════════════════

class Inventario(models.Model):
    """Stock de un producto en una sucursal."""
    producto        = models.ForeignKey(ProductoPOS, on_delete=models.CASCADE, related_name='inventarios')
    sucursal        = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='inventarios')
    stock_actual    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_minimo    = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text='Alerta Telegram cuando llegue a este nivel')
    stock_maximo    = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)
    costo_promedio  = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                          help_text='Costo promedio ponderado')
    ultimo_movimiento = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('producto', 'sucursal')
        verbose_name = 'Inventario'
        verbose_name_plural = 'Inventario'

    def __str__(self):
        return f'{self.producto.nombre} | {self.sucursal.nombre} | Stock: {self.stock_actual}'

    @property
    def bajo_minimo(self):
        return self.stock_actual <= self.stock_minimo and self.stock_minimo > 0

    @property
    def porcentaje_stock(self):
        if self.stock_maximo > 0:
            return min(100, int((self.stock_actual / self.stock_maximo) * 100))
        return None


class MovimientoInventario(models.Model):
    """Registro de entradas, salidas y ajustes de inventario."""
    TIPO_CHOICES = [
        ('entrada',  'Entrada de mercancía'),
        ('salida',   'Salida por venta'),
        ('ajuste',   'Ajuste manual'),
        ('devolucion','Devolución'),
        ('traslado', 'Traslado entre sucursales'),
    ]
    inventario  = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name='movimientos')
    tipo        = models.CharField(max_length=15, choices=TIPO_CHOICES)
    cantidad    = models.DecimalField(max_digits=12, decimal_places=2)
    stock_antes = models.DecimalField(max_digits=12, decimal_places=2)
    stock_despues = models.DecimalField(max_digits=12, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referencia  = models.CharField(max_length=200, blank=True, help_text='Nº venta, compra, etc.')
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    compra      = models.ForeignKey('CompraProveedor', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='movimientos')
    fecha       = models.DateTimeField(auto_now_add=True)
    notas       = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario'

    def __str__(self):
        return f'{self.get_tipo_display()} | {self.inventario.producto.nombre} | {self.cantidad}'


# ══════════════════════════════════════════════════════════
#  VENTAS / POS
# ══════════════════════════════════════════════════════════

class Venta(models.Model):
    ESTADO_CHOICES = [
        ('abierta',    'Abierta'),
        ('pagada',     'Pagada'),
        ('cancelada',  'Cancelada'),
        ('credito',    'A crédito'),
    ]
    PAGO_CHOICES = [
        ('efectivo',   'Efectivo'),
        ('tarjeta',    'Tarjeta'),
        ('transferencia', 'Transferencia'),
        ('credito',    'Crédito / Anticipo'),
        ('mixto',      'Pago mixto'),
    ]
    sucursal        = models.ForeignKey(Sucursal, on_delete=models.PROTECT, related_name='ventas')
    cajero          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, related_name='ventas_realizadas')
    folio           = models.CharField(max_length=30, unique=True)
    estado          = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='abierta')
    forma_pago      = models.CharField(max_length=20, choices=PAGO_CHOICES, default='efectivo')
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total           = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_pagado    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_total     = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text='Costo real para calcular ganancia')
    monto_recibido  = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text='Efectivo entregado por el cliente')
    cambio          = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text='Cambio devuelto al cliente')
    notas           = models.TextField(blank=True)
    creado          = models.DateTimeField(auto_now_add=True)
    actualizado     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering = ['-creado']

    def __str__(self):
        return f'Venta {self.folio} | {self.sucursal.nombre} | ${self.total}'

    @property
    def ganancia(self):
        return self.total - self.costo_total - self.descuento

    def save(self, *args, **kwargs):
        if not self.folio:
            ultimo = Venta.objects.filter(sucursal=self.sucursal).count() + 1
            self.folio = f'{self.sucursal.nombre[:3].upper()}-{ultimo:06d}'
        self.saldo_pendiente = max(Decimal('0'), self.total - self.total_pagado)
        super().save(*args, **kwargs)


class DetalleVenta(models.Model):
    venta           = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto        = models.ForeignKey(ProductoPOS, on_delete=models.PROTECT)
    cantidad        = models.DecimalField(max_digits=12, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2)
    nivel_precio    = models.PositiveSmallIntegerField(default=1,
                      help_text='1=menudeo, 2=mayoreo, 3=especial')

    class Meta:
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalles de Venta'

    def save(self, *args, **kwargs):
        self.subtotal = (self.precio_unitario - self.descuento) * self.cantidad
        super().save(*args, **kwargs)


class Abono(models.Model):
    """Abono a una venta a crédito."""
    FORMA_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('tarjeta',  'Tarjeta'),
        ('transferencia', 'Transferencia'),
    ]
    venta       = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='abonos')
    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    forma_pago  = models.CharField(max_length=20, choices=FORMA_CHOICES, default='efectivo')
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notas       = models.TextField(blank=True)
    fecha       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Abono'
        verbose_name_plural = 'Abonos'

    def __str__(self):
        return f'Abono ${self.monto} → {self.venta.folio}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar total pagado y saldo en la venta
        venta = self.venta
        venta.total_pagado = sum(a.monto for a in venta.abonos.all())
        venta.saldo_pendiente = max(Decimal('0'), venta.total - venta.total_pagado)
        if venta.saldo_pendiente == 0:
            venta.estado = 'pagada'
        venta.save()


class Anticipo(models.Model):
    """Anticipo para pedido antes de surtir."""
    sucursal    = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='anticipos')
    cliente_nombre = models.CharField(max_length=200)
    cliente_tel = models.CharField(max_length=20, blank=True)
    descripcion = models.TextField(help_text='Descripción del pedido')
    total_pedido = models.DecimalField(max_digits=12, decimal_places=2)
    anticipo_pagado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    saldo       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    entregado   = models.BooleanField(default=False)
    venta       = models.OneToOneField(Venta, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='anticipo')
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_prometida = models.DateField(null=True, blank=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Anticipo / Pedido'
        verbose_name_plural = 'Anticipos / Pedidos'

    def __str__(self):
        return f'Anticipo {self.cliente_nombre} | ${self.anticipo_pagado}/${self.total_pedido}'

    def save(self, *args, **kwargs):
        self.saldo = max(Decimal('0'), self.total_pedido - self.anticipo_pagado)
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════
#  PROVEEDORES Y COMPRAS
# ══════════════════════════════════════════════════════════

class Proveedor(models.Model):
    nombre      = models.CharField(max_length=200)
    rfc         = models.CharField(max_length=20, blank=True)
    contacto    = models.CharField(max_length=200, blank=True)
    telefono    = models.CharField(max_length=20, blank=True)
    email       = models.EmailField(blank=True)
    direccion   = models.TextField(blank=True)
    notas       = models.TextField(blank=True)
    activo      = models.BooleanField(default=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class CompraProveedor(models.Model):
    """Registro de una compra/entrada de mercancía."""
    ESTADO_CHOICES = [
        ('pendiente',  'Pendiente'),
        ('recibida',   'Recibida'),
        ('parcial',    'Parcial'),
        ('cancelada',  'Cancelada'),
    ]
    proveedor   = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='compras')
    sucursal    = models.ForeignKey(Sucursal, on_delete=models.PROTECT, related_name='compras')
    folio       = models.CharField(max_length=50, blank=True, help_text='Folio/número del ticket del proveedor')
    estado      = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente')
    total       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecha_compra = models.DateField(default=timezone.now)
    ticket_imagen = models.ImageField(upload_to='pos/tickets/', blank=True, null=True,
                                      help_text='Foto del ticket/factura del proveedor')
    ticket_pdf  = models.FileField(upload_to='pos/tickets/', blank=True, null=True)
    analisis_ocr = models.TextField(blank=True, help_text='Texto extraído del ticket por OCR/IA')
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notas       = models.TextField(blank=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Compra a Proveedor'
        verbose_name_plural = 'Compras a Proveedores'
        ordering = ['-fecha_compra']

    def __str__(self):
        return f'Compra {self.folio or self.pk} | {self.proveedor.nombre} | ${self.total}'


class DetalleCompra(models.Model):
    """Detalle de cada producto en una compra."""
    compra          = models.ForeignKey(CompraProveedor, on_delete=models.CASCADE, related_name='detalles')
    producto        = models.ForeignKey(ProductoPOS, on_delete=models.PROTECT)
    cantidad        = models.DecimalField(max_digits=12, decimal_places=2)
    costo_unitario  = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Detalle de Compra'
        verbose_name_plural = 'Detalles de Compra'

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.costo_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.producto.nombre} x{self.cantidad} @ ${self.costo_unitario}'


class PrecioHistoricoProveedor(models.Model):
    """Historial de precios de cada producto por proveedor para comparar."""
    proveedor       = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name='precios_historicos')
    producto        = models.ForeignKey(ProductoPOS, on_delete=models.CASCADE, related_name='precios_proveedores')
    costo           = models.DecimalField(max_digits=10, decimal_places=2)
    fecha           = models.DateField()
    compra          = models.ForeignKey(CompraProveedor, on_delete=models.SET_NULL,
                                        null=True, blank=True)
    notas           = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Precio Histórico Proveedor'
        verbose_name_plural = 'Precios Históricos Proveedores'

    def __str__(self):
        return f'{self.proveedor.nombre} | {self.producto.nombre} | ${self.costo} ({self.fecha})'


# ══════════════════════════════════════════════════════════
#  CONFIGURACIÓN GLOBAL DEL POS
# ══════════════════════════════════════════════════════════

class ConfigPOS(models.Model):
    """Parámetros globales del POS. Solo debe existir un registro (singleton)."""
    pct_reinversion = models.DecimalField(
        '% Reinversión sugerida', max_digits=5, decimal_places=2, default=Decimal('40.00'),
        help_text='Porcentaje de la ganancia neta sugerido para reinvertir en mercancía.'
    )
    whatsapp_general = models.CharField(
        'WhatsApp general', max_length=20, blank=True,
        help_text='Número sin +52 ni espacios. Se usa en tickets si la sucursal no tiene uno propio.'
    )

    class Meta:
        verbose_name = 'Configuración POS'
        verbose_name_plural = 'Configuración POS'

    def __str__(self):
        return f'Config POS — reinversión {self.pct_reinversion}%'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ══════════════════════════════════════════════════════════
#  GASTOS FIJOS POR SUCURSAL
# ══════════════════════════════════════════════════════════

class SolicitudCancelacion(models.Model):
    """Token temporal para autorizar cancelación de venta vía URL de Telegram."""
    venta          = models.ForeignKey('Venta', on_delete=models.CASCADE, related_name='solicitudes_cancelacion')
    token          = models.CharField(max_length=64, unique=True)
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       related_name='solicitudes_cancelacion')
    creado         = models.DateTimeField(auto_now_add=True)
    usado          = models.BooleanField(default=False)

    class Meta:
        verbose_name        = 'Solicitud de Cancelación'
        verbose_name_plural = 'Solicitudes de Cancelación'

    def __str__(self):
        return f'Cancelación {self.venta.folio} — {"usada" if self.usado else "pendiente"}'

    def expirado(self):
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() > self.creado + timedelta(minutes=30)


class GastoFijo(models.Model):
    TIPO_CHOICES = [
        ('renta',          'Renta / local'),
        ('sueldos',        'Sueldos y salarios'),
        ('internet',       'Internet'),
        ('electricidad',   'Electricidad / luz'),
        ('agua',           'Agua'),
        ('telefono',       'Teléfono / celular'),
        ('mantenimiento',  'Mantenimiento'),
        ('publicidad',     'Publicidad / marketing'),
        ('contabilidad',   'Contabilidad / honorarios'),
        ('otros',          'Otros'),
    ]

    sucursal    = models.ForeignKey(Sucursal, on_delete=models.CASCADE,
                                    related_name='gastos_fijos', verbose_name='Sucursal')
    tipo        = models.CharField('Tipo', max_length=20, choices=TIPO_CHOICES)
    descripcion = models.CharField('Descripción', max_length=200, blank=True)
    monto       = models.DecimalField('Monto mensual ($)', max_digits=10, decimal_places=2)
    activo      = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name        = 'Gasto Fijo'
        verbose_name_plural = 'Gastos Fijos'
        ordering            = ['sucursal', 'tipo']

    def __str__(self):
        label = dict(self.TIPO_CHOICES).get(self.tipo, self.tipo)
        return f'{self.sucursal.nombre} — {label}: ${self.monto}'


# ══════════════════════════════════════════════════════════
#  GASTOS OPERATIVOS (variables por evento)
# ══════════════════════════════════════════════════════════

class GastoOperativo(models.Model):
    TIPO_CHOICES = [
        ('traspaso',   'Pago de traspaso'),
        ('compra',     'Compra de mercancía'),
        ('servicio',   'Servicio / reparación'),
        ('otro',       'Otro'),
    ]
    sucursal    = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='gastos_operativos')
    tipo        = models.CharField(max_length=20, choices=TIPO_CHOICES)
    descripcion = models.CharField(max_length=300)
    monto       = models.DecimalField(max_digits=12, decimal_places=2)
    fecha       = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    referencia  = models.CharField(max_length=50, blank=True, help_text='Folio de traspaso, compra, etc.')

    class Meta:
        verbose_name        = 'Gasto Operativo'
        verbose_name_plural = 'Gastos Operativos'
        ordering            = ['-fecha']

    def __str__(self):
        return f'{self.sucursal.nombre} | {self.get_tipo_display()} | ${self.monto}'


# ══════════════════════════════════════════════════════════
#  TRASPASOS ENTRE SUCURSALES
# ══════════════════════════════════════════════════════════

class TraspasoSucursal(models.Model):
    ESTADO_CHOICES = [
        ('solicitado', 'Solicitado'),
        ('aprobado',   'Aprobado / En camino'),
        ('recibido',   'Recibido'),
        ('cancelado',  'Cancelado'),
    ]
    folio           = models.CharField(max_length=20, unique=True)
    sucursal_origen = models.ForeignKey(Sucursal, on_delete=models.PROTECT,
                                        related_name='traspasos_salida')
    sucursal_destino= models.ForeignKey(Sucursal, on_delete=models.PROTECT,
                                        related_name='traspasos_entrada')
    solicitado_por  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, related_name='traspasos_solicitados')
    aprobado_por    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='traspasos_aprobados')
    recibido_por    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='traspasos_recibidos')
    estado          = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='solicitado')
    notas           = models.TextField(blank=True)
    # Campos financieros
    total           = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text='Total a pagar por el destino al origen')
    pagado          = models.BooleanField(default=False)
    forma_pago      = models.CharField(max_length=20, blank=True,
                                       choices=[('efectivo','Efectivo'),('transferencia','Transferencia'),('credito','A crédito')])
    venta_origen    = models.OneToOneField('Venta', on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='traspaso')
    creado          = models.DateTimeField(auto_now_add=True)
    aprobado_en     = models.DateTimeField(null=True, blank=True)
    recibido_en     = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Traspaso entre Sucursales'
        verbose_name_plural = 'Traspasos entre Sucursales'
        ordering            = ['-creado']

    def __str__(self):
        return f'{self.folio} {self.sucursal_origen} → {self.sucursal_destino}'


class DetalleTraspaso(models.Model):
    traspaso        = models.ForeignKey(TraspasoSucursal, on_delete=models.CASCADE,
                                        related_name='detalles')
    producto        = models.ForeignKey(ProductoPOS, on_delete=models.PROTECT)
    cantidad        = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_recibida = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                            help_text='Puede diferir si llegó incompleto')
    costo_unitario       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_traspaso_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                               help_text='Precio de traspaso (P4) al momento de crear')
    subtotal_traspaso    = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Detalle de Traspaso'

    def __str__(self):
        return f'{self.producto.nombre} × {self.cantidad}'


# ══════════════════════════════════════════════════════════
#  RECARGAS Y PAGOS DE SERVICIO
# ══════════════════════════════════════════════════════════

class TransaccionServicio(models.Model):
    TIPO_CHOICES = [
        ('recarga',  'Recarga de celular'),
        ('servicio', 'Pago de servicio'),
    ]
    SERVICIO_CHOICES = [
        ('cfe',       'CFE / Luz'),
        ('telmex',    'Telmex / Internet'),
        ('agua',      'Agua'),
        ('gas',       'Gas'),
        ('telcel',    'Telcel'),
        ('att',       'AT&T'),
        ('movistar',  'Movistar'),
        ('bait',      'Bait'),
        ('otro',      'Otro'),
    ]
    sucursal    = models.ForeignKey('Sucursal', on_delete=models.PROTECT, related_name='transacciones_servicio')
    cajero      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    tipo        = models.CharField(max_length=10, choices=TIPO_CHOICES)
    servicio    = models.CharField(max_length=20, choices=SERVICIO_CHOICES, blank=True,
                                   help_text='Solo para pagos de servicio')
    telefono    = models.CharField(max_length=15, blank=True,
                                   help_text='Número recargado (solo recargas)')
    referencia  = models.CharField(max_length=100, blank=True,
                                   help_text='Número de cuenta, contrato, etc.')
    monto       = models.DecimalField('Monto cobrado al cliente ($)', max_digits=10, decimal_places=2)
    comision    = models.DecimalField('Comisión ($)', max_digits=6, decimal_places=2, default=1)
    fecha       = models.DateTimeField(auto_now_add=True)
    notas       = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name        = 'Transacción de Servicio'
        verbose_name_plural = 'Transacciones de Servicio'
        ordering            = ['-fecha']

    def __str__(self):
        return f'{self.get_tipo_display()} ${self.monto} — com. ${self.comision}'


# ══════════════════════════════════════════════════════════
#  CAJA DIARIA
# ══════════════════════════════════════════════════════════

class CierreCaja(models.Model):
    ESTADO_CHOICES = [
        ('abierta',  'Abierta'),
        ('cerrada',  'Cerrada'),
    ]
    sucursal         = models.ForeignKey(Sucursal, on_delete=models.PROTECT, related_name='cierres_caja')
    fecha            = models.DateField()
    estado           = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')

    # Apertura
    cambio_inicial   = models.DecimalField('Cambio inicial ($)', max_digits=10, decimal_places=2, default=0)
    usuario_apertura = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                         null=True, related_name='aperturas_caja')
    apertura_en      = models.DateTimeField(auto_now_add=True)

    # Cierre
    efectivo_contado = models.DecimalField('Efectivo contado al cierre ($)', max_digits=10,
                                           decimal_places=2, null=True, blank=True)
    usuario_cierre   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='cierres_caja')
    cierre_en        = models.DateTimeField(null=True, blank=True)
    notas_cierre     = models.TextField(blank=True)

    # Calculados al cerrar (guardados para histórico)
    total_ventas_efectivo  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_retiros          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_gastos_efectivo  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_monto_servicios  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_comisiones       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    efectivo_esperado      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    diferencia             = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                                help_text='Positivo = sobra, Negativo = falta')

    # Revisión por gerente/admin
    revisado_por   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='cierres_revisados')
    revisado_en    = models.DateTimeField(null=True, blank=True)
    notas_revision = models.TextField(blank=True)

    class Meta:
        unique_together     = ('sucursal', 'fecha')
        verbose_name        = 'Cierre de Caja'
        verbose_name_plural = 'Cierres de Caja'
        ordering            = ['-fecha']

    def __str__(self):
        return f'{self.sucursal.nombre} — {self.fecha} ({self.get_estado_display()})'


class RetiroEfectivo(models.Model):
    caja        = models.ForeignKey(CierreCaja, on_delete=models.CASCADE, related_name='retiros')
    monto       = models.DecimalField(max_digits=10, decimal_places=2)
    motivo      = models.CharField(max_length=200)
    usuario     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Retiro de Efectivo'
        verbose_name_plural = 'Retiros de Efectivo'
        ordering            = ['-fecha']

    def __str__(self):
        return f'Retiro ${self.monto} — {self.caja}'
