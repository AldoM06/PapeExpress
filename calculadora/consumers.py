import json
import os
import uuid
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class CalculadoraConsumer(AsyncWebsocketConsumer):
    """
    Canal WebSocket personal por sesión de cálculo.
    Cada cliente obtiene un canal único — el servidor le envía el progreso.
    """

    async def connect(self):
        # Nombre de canal único para este cliente
        self.channel_name_key = self.channel_name
        await self.accept()
        # Enviar el nombre del canal al cliente para que lo use en el POST
        await self.send(json.dumps({
            'tipo': 'canal_listo',
            'channel_name': self.channel_name,
        }))

    async def disconnect(self, code):
        pass

    async def receive(self, text_data):
        """El cliente puede enviar ping para mantener viva la conexión."""
        data = json.loads(text_data)
        if data.get('tipo') == 'ping':
            await self.send(json.dumps({'tipo': 'pong'}))

    # ── Handlers de mensajes del servidor ────────────────
    async def calculadora_progreso(self, event):
        """Recibe actualizaciones del hilo worker y las reenvía al browser."""
        payload = {k: v for k, v in event.items() if k != 'type'}
        await self.send(json.dumps(payload))
