from django.db import models


class Categoria(models.Model):
    TIPO_CHOICES = [
        ('reventa', 'Producto de Reventa'),
        ('fabricado', 'Producto Fabricado'),
    ]
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='reventa')
    descripcion = models.TextField(blank=True)
    icono = models.CharField(max_length=50, blank=True, help_text='Clase de ícono Bootstrap Icons, ej: bi-pencil')

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'


class Producto(models.Model):
    categoria      = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    nombre         = models.CharField(max_length=200)
    descripcion    = models.TextField(blank=True)
    imagen         = models.ImageField(upload_to='productos/', blank=True, null=True)
    precio         = models.DecimalField('Precio menudeo', max_digits=10, decimal_places=2, null=True, blank=True)
    precio_mayoreo = models.DecimalField('Precio mayoreo', max_digits=10, decimal_places=2, null=True, blank=True)
    peso           = models.DecimalField('Peso (kg)', max_digits=6, decimal_places=3, default=0)
    # Detalles del producto
    marca          = models.CharField('Marca', max_length=100, blank=True)
    piezas_por_caja = models.PositiveIntegerField('Piezas por caja/paquete', null=True, blank=True,
                       help_text='Cuántas piezas trae la presentación de mayoreo')
    contenido      = models.CharField('Contenido / presentación', max_length=200, blank=True,
                       help_text='Ej: Caja con 12 pzas, Bolsa 100 hojas, Paquete x 6')
    sku            = models.CharField('SKU / Código', max_length=100, blank=True)
    disponible     = models.BooleanField(default=True)
    mostrar_en_portada = models.BooleanField(default=False, verbose_name='Mostrar en portada')
    destacado      = models.BooleanField(default=False)
    orden          = models.PositiveIntegerField(default=0)
    creado         = models.DateTimeField(auto_now_add=True)
    actualizado    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class FotoProducto(models.Model):
    """Fotos adicionales de un producto (galería)."""
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='fotos')
    imagen   = models.ImageField(upload_to='productos/galeria/')
    orden    = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Foto de producto'
        verbose_name_plural = 'Fotos de producto'

    def __str__(self):
        return f'Foto {self.orden} — {self.producto.nombre}'


class MensajeContacto(models.Model):
    nombre = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=20, blank=True)
    asunto = models.CharField(max_length=300)
    mensaje = models.TextField()
    leido = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mensaje de Contacto'
        verbose_name_plural = 'Mensajes de Contacto'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.nombre} - {self.asunto}'


class ConfiguracionSitio(models.Model):
    """Singleton para configuración general del sitio."""
    historia = models.TextField(verbose_name='Historia de la empresa',
                                 default='PapeExpress nació con la visión de llevar papelería de calidad a todos.')
    mision = models.TextField(blank=True)
    vision = models.TextField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Configuración del Sitio'
        verbose_name_plural = 'Configuración del Sitio'

    def __str__(self):
        return 'Configuración del Sitio'

    def save(self, *args, **kwargs):
        self.pk = 1  # Solo puede existir uno
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
