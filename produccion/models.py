from django.db import models
from accounts.models import Usuario


ETAPAS = [
    ('propuesta',      'Propuesta'),
    ('diseño',         'Diseño'),
    ('armado_digital', 'Armado Digital'),
    ('muestra',        'Muestra'),
    ('materiales',     'Materiales y Costos'),
    ('corte',          'Corte'),
    ('armado',         'Armado'),
    ('embolsado',      'Embolsado'),
    ('etiquetado',     'Etiquetado'),
    ('terminado',      'Terminado'),
]

ETAPA_COLORES = {
    'propuesta':      '#6c757d',
    'diseño':         '#0dcaf0',
    'armado_digital': '#0d6efd',
    'muestra':        '#6f42c1',
    'materiales':     '#fd7e14',
    'corte':          '#ffc107',
    'armado':         '#20c997',
    'embolsado':      '#198754',
    'etiquetado':     '#0a58ca',
    'terminado':      '#28a745',
}


class FiguraFomy(models.Model):
    nombre               = models.CharField(max_length=200)
    descripcion          = models.TextField(blank=True)
    imagen_referencia    = models.ImageField(upload_to='figuras/imagenes/', blank=True, null=True)
    etapa_actual         = models.CharField(max_length=30, choices=ETAPAS, default='propuesta')
    responsable          = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='figuras_responsable'
    )
    cantidad_planificada = models.PositiveIntegerField(default=0)
    cantidad_disponible  = models.PositiveIntegerField(default=0,
        help_text='Piezas listas para venta / pedidos de socios')
    costo_estimado       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_venta         = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tiene_fomy           = models.BooleanField(default=False, verbose_name='¿Hay fomy disponible?')
    notas                = models.TextField(blank=True)
    creado               = models.DateTimeField(auto_now_add=True)
    actualizado          = models.DateTimeField(auto_now=True)

    # ── Archivos de producción ──────────────────────
    archivo_studio3      = models.FileField(
        upload_to='figuras/studio3/', blank=True, null=True,
        verbose_name='Plantilla Studio3',
        help_text='Archivo .studio3 para la máquina de corte'
    )
    archivo_instrucciones_pdf = models.FileField(
        upload_to='figuras/instrucciones/', blank=True, null=True,
        verbose_name='Instrucciones PDF',
        help_text='PDF con instrucciones de armado'
    )
    archivo_instrucciones_word = models.FileField(
        upload_to='figuras/instrucciones/', blank=True, null=True,
        verbose_name='Instrucciones Word (.docx)',
        help_text='Word editable con instrucciones de armado'
    )

    class Meta:
        verbose_name = 'Figura de Fomy'
        verbose_name_plural = 'Figuras de Fomy'
        ordering = ['-actualizado']


    def get_etapa_display_for(self, etapa_key):
        return dict(ETAPAS).get(etapa_key, etapa_key)
    def __str__(self):
        return f'{self.nombre} [{self.get_etapa_actual_display()}]'

    @property
    def color_etapa(self):
        return ETAPA_COLORES.get(self.etapa_actual, '#6c757d')

    @property
    def porcentaje_avance(self):
        etapas_lista = [e[0] for e in ETAPAS]
        try:
            idx = etapas_lista.index(self.etapa_actual)
            return int((idx / (len(etapas_lista) - 1)) * 100)
        except ValueError:
            return 0


class FotoFigura(models.Model):
    """Hasta 4 fotos de referencia por figura."""
    figura      = models.ForeignKey(FiguraFomy, on_delete=models.CASCADE, related_name='fotos')
    foto        = models.ImageField(upload_to='figuras/fotos/')
    descripcion = models.CharField(max_length=200, blank=True)
    orden       = models.PositiveSmallIntegerField(default=0)
    subida      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden', 'subida']
        verbose_name = 'Foto de Figura'
        verbose_name_plural = 'Fotos de Figura'


    def get_etapa_display_for(self, etapa_key):
        return dict(ETAPAS).get(etapa_key, etapa_key)
    def __str__(self):
        return f'Foto {self.orden} — {self.figura.nombre}'


class HistorialEtapa(models.Model):
    figura         = models.ForeignKey(FiguraFomy, on_delete=models.CASCADE, related_name='historial')
    etapa_anterior = models.CharField(max_length=30, choices=ETAPAS)
    etapa_nueva    = models.CharField(max_length=30, choices=ETAPAS)
    usuario        = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True)
    notas          = models.TextField(blank=True)
    fecha          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Historial de Etapa'
        verbose_name_plural = 'Historial de Etapas'


class Libreta(models.Model):
    nombre          = models.CharField(max_length=200)
    descripcion     = models.TextField(blank=True)
    imagen          = models.ImageField(upload_to='libretas/', blank=True, null=True)
    num_hojas       = models.PositiveIntegerField(default=100)
    tipo_pasta      = models.CharField(max_length=100, blank=True)
    precio          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    disponible      = models.BooleanField(default=True)
    mostrar_en_portada = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Libreta'
        verbose_name_plural = 'Libretas'
        ordering = ['nombre']


    def get_etapa_display_for(self, etapa_key):
        return dict(ETAPAS).get(etapa_key, etapa_key)
    def __str__(self):
        return self.nombre
