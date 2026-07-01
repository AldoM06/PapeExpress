from django.conf import settings
from django.db import models


class Conversacion(models.Model):
    ESTADO = [
        ('abierta',   'Abierta'),
        ('atendida',  'Con agente'),
        ('cerrada',   'Cerrada'),
    ]
    cliente            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                           null=True, blank=True, related_name='conversaciones_chat')
    # Datos de visitante anónimo
    visitante_nombre   = models.CharField(max_length=100, blank=True)
    visitante_telefono = models.CharField(max_length=20, blank=True)
    visitante_email    = models.EmailField(blank=True)

    agente           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='chats_atendidos')
    estado           = models.CharField(max_length=20, choices=ESTADO, default='abierta')
    telegram_msg_id  = models.BigIntegerField(null=True, blank=True)
    creada           = models.DateTimeField(auto_now_add=True)
    cerrada          = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creada']
        verbose_name = 'Conversación'
        verbose_name_plural = 'Conversaciones'

    def nombre_contacto(self):
        if self.cliente:
            return self.cliente.get_full_name() or self.cliente.username
        return self.visitante_nombre or 'Visitante'

    def __str__(self):
        return f'Chat #{self.id} — {self.nombre_contacto()}'


class Mensaje(models.Model):
    ORIGEN = [
        ('cliente', 'Cliente'),
        ('agente',  'Agente'),
        ('sistema', 'Sistema'),
    ]
    conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, related_name='mensajes')
    origen       = models.CharField(max_length=10, choices=ORIGEN)
    texto        = models.TextField()
    enviado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['enviado']

    def __str__(self):
        return f'[{self.origen}] {self.texto[:60]}'
