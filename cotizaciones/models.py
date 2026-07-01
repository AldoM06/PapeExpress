from django.conf import settings
from django.db import models
from decimal import Decimal


class TarifaEnvio(models.Model):
    """Configuración de tarifas de envío PapeExpress. Solo debe existir un registro."""
    precio_base     = models.DecimalField('Precio base ($)', max_digits=8, decimal_places=2, default=180)
    peso_base_kg    = models.DecimalField('Peso base incluido (kg)', max_digits=6, decimal_places=2, default=5)
    precio_kg_extra = models.DecimalField('Precio por kg extra ($)', max_digits=8, decimal_places=2, default=30)
    activa          = models.BooleanField('Tarifa activa', default=True)

    class Meta:
        verbose_name = 'Tarifa de Envío PapeExpress'
        verbose_name_plural = 'Tarifas de Envío PapeExpress'

    def __str__(self):
        return f'${self.precio_base} base ({self.peso_base_kg} kg) + ${self.precio_kg_extra}/kg extra'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def calcular(self, peso_kg: Decimal) -> Decimal:
        """Calcula el costo de envío PapeExpress para un peso dado."""
        peso = Decimal(str(peso_kg))
        if peso <= self.peso_base_kg:
            return self.precio_base
        kg_extra = peso - self.peso_base_kg
        return self.precio_base + (kg_extra * self.precio_kg_extra)


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
