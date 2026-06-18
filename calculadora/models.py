from django.db import models
from django.conf import settings


class PlanCalculadora(models.Model):
    """Define límites de peso por tipo de usuario."""
    PLAN_CHOICES = [
        ('basico',    'Básico (sin sesión)'),
        ('cliente',   'Cliente registrado'),
        ('socio',     'Socio Comercial'),
        ('premium',   'Premium / Staff'),
    ]
    plan        = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    max_mb      = models.PositiveIntegerField(default=10, help_text='Límite en MB')
    max_paginas = models.PositiveIntegerField(default=50, help_text='Máx. páginas por cálculo')
    descripcion = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = 'Plan de Calculadora'
        verbose_name_plural = 'Planes de Calculadora'

    def __str__(self):
        return f'{self.get_plan_display()} — {self.max_mb} MB'


class HistorialCalculo(models.Model):
    """Registro de cada cálculo realizado."""
    usuario       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calculos'
    )
    nombre_archivo = models.CharField(max_length=255)
    num_paginas    = models.PositiveIntegerField(default=0)
    tipo_hoja      = models.CharField(max_length=30, default='bond')
    precio_minimo  = models.DecimalField(max_digits=8, decimal_places=2)
    precio_maximo  = models.DecimalField(max_digits=8, decimal_places=2)
    costo_total    = models.DecimalField(max_digits=10, decimal_places=2)
    costo_promedio = models.DecimalField(max_digits=8,  decimal_places=2, default=0)
    tiempo_proceso = models.FloatField(default=0, help_text='Segundos')
    ip_cliente     = models.GenericIPAddressField(null=True, blank=True)
    creado         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de Cálculo'
        verbose_name_plural = 'Historial de Cálculos'
        ordering = ['-creado']

    def __str__(self):
        return f'{self.nombre_archivo} — ${self.costo_total} ({self.creado:%d/%m/%Y})'
