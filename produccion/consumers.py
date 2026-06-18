import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ProduccionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add('produccion', self.channel_name)
        await self.accept()
        # Enviar estado inicial
        figuras = await self.get_figuras()
        await self.send(text_data=json.dumps({'tipo': 'estado_inicial', 'figuras': figuras}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('produccion', self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('tipo') == 'ping':
            await self.send(text_data=json.dumps({'tipo': 'pong'}))

    async def actualizacion_figura(self, event):
        await self.send(text_data=json.dumps(event['data']))

    @database_sync_to_async
    def get_figuras(self):
        from .models import FiguraFomy
        figuras = FiguraFomy.objects.all().order_by('-actualizado')[:20]
        return [
            {
                'id': f.id,
                'nombre': f.nombre,
                'etapa': f.etapa_actual,
                'etapa_display': f.get_etapa_actual_display(),
                'color': f.color_etapa,
                'porcentaje': f.porcentaje_avance,
                'actualizado': f.actualizado.strftime('%d/%m/%Y %H:%M'),
            }
            for f in figuras
        ]
