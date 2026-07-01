from django.conf import settings
from django.db import models
from decimal import Decimal


class TarifaEnvio(models.Model):
    """Configuración de tarifas de envío PapeExpress. Solo debe existir un registro."""
    precio_base     = models.DecimalField('Precio base ($)', max_digits=8, decimal_places=2, default=180)
    peso_base_kg    = models.DecimalField('Peso base incluido (kg)', max_digits=6, decimal_places=2, default=5)
    precio_kg_extra = models.DecimalField('Precio por kg extra ($)', max_digits=8, decimal_places=2, default=30)
    activa          = models.BooleanField('Tarifa activa', default=True)

    # ── Promoción por fechas ──────────────────────────────
    promo_activa    = models.BooleanField('Promo por fechas activa', default=False)
    promo_precio    = models.DecimalField('Precio con promo ($)', max_digits=8, decimal_places=2,
                       null=True, blank=True,
                       help_text='Precio fijo de envío durante la promo. Ej: $120')
    promo_inicio    = models.DateField('Inicio de promo', null=True, blank=True)
    promo_fin       = models.DateField('Fin de promo', null=True, blank=True)
    promo_etiqueta  = models.CharField('Etiqueta promo', max_length=80, blank=True,
                       help_text='Texto que ve el cliente. Ej: "¡Envío especial de temporada!"')

    # ── Envío gratis / descuento por monto mínimo ────────
    monto_minimo_promo   = models.DecimalField('Monto mínimo para promo ($)', max_digits=10, decimal_places=2,
                            null=True, blank=True,
                            help_text='Si el subtotal del pedido supera este monto se aplica el precio especial')
    precio_monto_minimo  = models.DecimalField('Precio de envío con monto mínimo ($)', max_digits=8, decimal_places=2,
                            null=True, blank=True,
                            help_text='Pon 0 para envío gratis. Ej: $0 o $50')
    monto_minimo_etiqueta = models.CharField('Etiqueta monto mínimo', max_length=80, blank=True,
                            help_text='Ej: "¡Envío gratis en compras mayores a $1,500!"')

    class Meta:
        verbose_name = 'Tarifa de Envío PapeExpress'
        verbose_name_plural = 'Tarifas de Envío PapeExpress'

    def __str__(self):
        return f'${self.precio_base} base ({self.peso_base_kg} kg) + ${self.precio_kg_extra}/kg extra'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def promo_fechas_vigente(self):
        """Retorna True si la promo por fechas está activa hoy."""
        from django.utils import timezone
        if not self.promo_activa or not self.promo_precio:
            return False
        hoy = timezone.now().date()
        inicio_ok = (self.promo_inicio is None) or (hoy >= self.promo_inicio)
        fin_ok    = (self.promo_fin    is None) or (hoy <= self.promo_fin)
        return inicio_ok and fin_ok

    def calcular(self, peso_kg: Decimal, subtotal: Decimal = Decimal('0')):
        """
        Calcula el costo de envío aplicando promos si corresponde.
        Prioridad: monto mínimo > promo por fechas > tarifa estándar.
        Retorna (costo, etiqueta_promo | None).
        """
        peso = Decimal(str(peso_kg))

        # 1. Promo por monto mínimo
        if (self.monto_minimo_promo and subtotal >= self.monto_minimo_promo
                and self.precio_monto_minimo is not None):
            return self.precio_monto_minimo, self.monto_minimo_etiqueta or '¡Descuento por volumen aplicado!'

        # 2. Promo por fechas
        if self.promo_fechas_vigente():
            return self.promo_precio, self.promo_etiqueta or '¡Precio especial de envío!'

        # 3. Tarifa estándar
        if peso <= self.peso_base_kg:
            return self.precio_base, None
        kg_extra = peso - self.peso_base_kg
        return self.precio_base + (kg_extra * self.precio_kg_extra), None


class Cotizacion(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('procesando', 'Procesando'),
        ('completada', 'Completada'),
        ('cancelada', 'Cancelada'),
    ]
    METODO_ENVIO = [
        ('papeexpress', 'Envío PapeExpress (CDMX / EdoMex)'),
        ('paqueteria',  'Paquetería (FedEx, DHL, etc.)'),
        ('recoger',     'Recoger en tienda'),
    ]
    cliente        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cotizaciones')
    estado         = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    notas          = models.TextField(blank=True)
    peso_total     = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    total_estimado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Envío
    metodo_envio   = models.CharField(max_length=20, choices=METODO_ENVIO, default='papeexpress')
    direccion_calle    = models.CharField('Calle y número', max_length=200, blank=True)
    direccion_colonia  = models.CharField('Colonia', max_length=100, blank=True)
    direccion_ciudad   = models.CharField('Ciudad / Municipio', max_length=100, blank=True)
    direccion_estado   = models.CharField('Estado', max_length=100, blank=True)
    direccion_cp       = models.CharField('Código postal', max_length=10, blank=True)
    fecha_requerida    = models.DateField('Fecha requerida', null=True, blank=True)
    notas_entrega      = models.TextField('Notas de entrega', blank=True)
    costo_envio        = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    creado         = models.DateTimeField(auto_now_add=True)
    actualizado    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        ordering = ['-creado']

    def __str__(self):
        return f'Cotización #{self.id} — {self.cliente}'


class DetalleCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('core.Producto', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.cantidad}x {self.producto.nombre}'
