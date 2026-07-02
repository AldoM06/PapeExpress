from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    ROL_CHOICES = [
        ('admin',     'Administrador'),
        ('operador',  'Operador PapeExpress'),  # ve pedidos + POS según sucursal
        ('cliente',   'Cliente'),
        ('socio',     'Socio Comercial'),
        ('ventas',    'Ventas'),
        ('almacen',   'Almacén'),
        ('diseño',    'Diseño'),
        ('produccion','Producción'),
    ]
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='cliente')
    empresa = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    foto = models.ImageField(upload_to='usuarios/', blank=True, null=True)
    foto_negocio = models.ImageField(upload_to='verificacion/', blank=True, null=True, verbose_name='Foto del negocio')
    verificado = models.BooleanField(default=False, verbose_name='Cliente verificado')
    # Tarifa de envío preferencial (si está definida, reemplaza la tarifa estándar)
    precio_envio_especial = models.DecimalField(
        'Tarifa de envío especial ($)', max_digits=8, decimal_places=2,
        null=True, blank=True,
        help_text='Si se define, este precio reemplaza la tarifa estándar PapeExpress para este cliente.'
    )
    # Dirección de envío por defecto
    dir_calle   = models.CharField('Calle y número', max_length=200, blank=True)
    dir_colonia = models.CharField('Colonia', max_length=100, blank=True)
    dir_ciudad  = models.CharField('Ciudad / Municipio', max_length=100, blank=True)
    dir_estado  = models.CharField('Estado', max_length=100, blank=True)
    dir_cp      = models.CharField('Código postal', max_length=10, blank=True)

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_rol_display()})'

    @property
    def es_admin(self):
        return self.rol == 'admin' or self.is_superuser

    @property
    def es_socio(self):
        return self.rol == 'socio'

    @property
    def es_cliente(self):
        return self.rol == 'cliente'
