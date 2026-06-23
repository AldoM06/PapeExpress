from django.db import models
from django.conf import settings


class SocioComercial(models.Model):
    nombre          = models.CharField(max_length=200)
    tipo_negocio    = models.CharField(max_length=100, blank=True)
    descripcion     = models.TextField(blank=True, help_text='Texto atractivo para clientes')
    slogan          = models.CharField(max_length=200, blank=True, help_text='Frase corta del negocio')
    logo            = models.ImageField(upload_to='socios/logos/', blank=True, null=True)
    foto_negocio    = models.ImageField(upload_to='socios/fotos/', blank=True, null=True)
    contacto        = models.CharField(max_length=200, blank=True)
    telefono        = models.CharField(max_length=20, blank=True)
    whatsapp_1      = models.CharField(max_length=20, blank=True,
                                       help_text='Número con código país, ej: 5215512345678')
    whatsapp_2      = models.CharField(max_length=20, blank=True,
                                       help_text='Segundo número WhatsApp (opcional)')
    facebook_url    = models.URLField(blank=True, help_text='URL completa del perfil/página de Facebook')
    instagram_url   = models.URLField(blank=True)
    email           = models.EmailField(blank=True)
    direccion       = models.CharField(max_length=300, blank=True)

    ciudad          = models.CharField(max_length=100, blank=True)
    estado          = models.CharField(max_length=100, blank=True)
    latitud         = models.FloatField(null=True, blank=True)
    longitud        = models.FloatField(null=True, blank=True)
    horario         = models.CharField(max_length=200, blank=True,
                                       help_text='Ej: Lun-Vie 9am-7pm, Sáb 9am-3pm')
    activo          = models.BooleanField(default=True)
    mostrar_en_mapa = models.BooleanField(default=True)
    destacado       = models.BooleanField(default=False,
                                          help_text='Aparece primero y con destacado visual')
    notas           = models.TextField(blank=True)
    usuario         = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perfil_socio'
    )
    creado          = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Socio Comercial'
        verbose_name_plural = 'Socios Comerciales'
        ordering = ['-destacado', 'nombre']

    def __str__(self):
        return self.nombre
    
    @property
    def whatsapp_1_url(self):
        if self.whatsapp_1:
            num = self.whatsapp_1.replace('+', '').replace(' ', '').replace('-', '')
            return f'https://wa.me/{num}'
        return ''

    @property
    def whatsapp_2_url(self):
        if self.whatsapp_2:
            num = self.whatsapp_2.replace('+', '').replace(' ', '').replace('-', '')
            return f'https://wa.me/{num}'
        return ''

    @property
    def maps_url(self):
        if self.latitud and self.longitud:
            return f'https://maps.google.com/?q={self.latitud},{self.longitud}'
        return ''




class PedidoFomy(models.Model):
    """Pedido de figuras de fomy realizado por un socio."""
    ESTADO_CHOICES = [
        ('pendiente',   'Pendiente de pago'),
        ('pagado',      'Pagado'),
        ('preparando',  'Preparando'),
        ('enviado',     'Enviado'),
        ('entregado',   'Entregado'),
        ('cancelado',   'Cancelado'),
    ]

    socio           = models.ForeignKey(SocioComercial, on_delete=models.CASCADE, related_name='pedidos')
    figura          = models.ForeignKey(
        'produccion.FiguraFomy', on_delete=models.PROTECT, related_name='pedidos'
    )
    cantidad        = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    total           = models.DecimalField(max_digits=12, decimal_places=2)
    estado          = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    notas           = models.TextField(blank=True)

    # Stripe
    stripe_session_id      = models.CharField(max_length=200, blank=True)
    stripe_payment_intent  = models.CharField(max_length=200, blank=True)
    pagado_en              = models.DateTimeField(null=True, blank=True)

    creado          = models.DateTimeField(auto_now_add=True)
    actualizado     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pedido de Fomy'
        verbose_name_plural = 'Pedidos de Fomy'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.socio.nombre} — {self.figura.nombre} x{self.cantidad}'

    def save(self, *args, **kwargs):
        self.total = self.precio_unitario * self.cantidad
        super().save(*args, **kwargs)
