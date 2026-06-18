from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    ROL_CHOICES = [
        ('admin', 'Administrador'),
        ('cliente', 'Cliente'),
        ('socio', 'Socio Comercial'),
        ('ventas', 'Ventas'),
        ('almacen', 'Almacén'),
        ('diseño', 'Diseño'),
        ('produccion', 'Producción'),
    ]
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='cliente')
    empresa = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    foto = models.ImageField(upload_to='usuarios/', blank=True, null=True)

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
