import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
            return

        self.conv_id = self.scope['url_route']['kwargs']['conv_id']
        self.group = f'chat_{self.conv_id}'

        # Verificar que el usuario tiene acceso a esta conversación
        if not await self.tiene_acceso(user, self.conv_id):
            await self.close()
            return

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        tipo = data.get('tipo', 'mensaje')
        user = self.scope['user']

        if tipo == 'mensaje':
            texto = data.get('texto', '').strip()
            if not texto:
                return

            es_agente = user.is_staff or user.is_superuser
            origen = 'agente' if es_agente else 'cliente'

            # Guardar mensaje en BD
            await self.guardar_mensaje(self.conv_id, origen, texto, agente=user if es_agente else None)

            # Broadcast a todos en el grupo
            await self.channel_layer.group_send(self.group, {
                'type': 'chat_mensaje',
                'origen': origen,
                'texto': texto,
                'nombre': user.get_full_name() or user.username,
            })

            # Si es cliente y la conv está en modo IA → responder con IA
            if not es_agente:
                conv = await self.get_conversacion(self.conv_id)
                if conv and conv.modo_ia:
                    historial = await self.get_historial_ia(self.conv_id)
                    from .ia import respuesta_ia
                    import asyncio
                    loop = asyncio.get_running_loop()
                    respuesta = await loop.run_in_executor(None, respuesta_ia, historial)
                    await self.guardar_mensaje(self.conv_id, 'ia', respuesta)
                    await self.channel_layer.group_send(self.group, {
                        'type': 'chat_mensaje',
                        'origen': 'ia',
                        'texto': respuesta,
                        'nombre': 'Asistente PapeExpress',
                    })

        elif tipo == 'tomar_chat':
            if user.is_staff or user.is_superuser:
                await self.asignar_agente(self.conv_id, user)
                await self.channel_layer.group_send(self.group, {
                    'type': 'chat_sistema',
                    'texto': f'{user.get_full_name() or user.username} se unió al chat.',
                })

        elif tipo == 'activar_ia':
            if user.is_staff or user.is_superuser:
                await self.toggle_ia(self.conv_id, True)
                await self.channel_layer.group_send(self.group, {
                    'type': 'chat_sistema',
                    'texto': 'Modo IA activado. El asistente responderá automáticamente.',
                })

        elif tipo == 'desactivar_ia':
            if user.is_staff or user.is_superuser:
                await self.toggle_ia(self.conv_id, False)
                await self.channel_layer.group_send(self.group, {
                    'type': 'chat_sistema',
                    'texto': 'Modo IA desactivado. Un agente tomará el chat.',
                })

        elif tipo == 'cerrar':
            if user.is_staff or user.is_superuser:
                await self.cerrar_conversacion(self.conv_id)
                await self.channel_layer.group_send(self.group, {
                    'type': 'chat_sistema',
                    'texto': 'Chat cerrado por el agente.',
                })

    async def chat_mensaje(self, event):
        await self.send(text_data=json.dumps({
            'tipo': 'mensaje',
            'origen': event['origen'],
            'texto': event['texto'],
            'nombre': event['nombre'],
        }))

    async def chat_sistema(self, event):
        await self.send(text_data=json.dumps({
            'tipo': 'sistema',
            'texto': event['texto'],
        }))

    # ── DB helpers ────────────────────────────────────────────────────────────

    @database_sync_to_async
    def tiene_acceso(self, user, conv_id):
        from .models import Conversacion
        try:
            conv = Conversacion.objects.get(pk=conv_id)
            return conv.cliente == user or user.is_staff or user.is_superuser
        except Conversacion.DoesNotExist:
            return False

    @database_sync_to_async
    def get_conversacion(self, conv_id):
        from .models import Conversacion
        try:
            return Conversacion.objects.get(pk=conv_id)
        except Conversacion.DoesNotExist:
            return None

    @database_sync_to_async
    def guardar_mensaje(self, conv_id, origen, texto, agente=None):
        from .models import Conversacion, Mensaje
        conv = Conversacion.objects.get(pk=conv_id)
        if agente and conv.estado == 'abierta':
            conv.estado = 'atendida'
            conv.agente = agente
            conv.save(update_fields=['estado', 'agente'])
        Mensaje.objects.create(conversacion=conv, origen=origen, texto=texto)

    @database_sync_to_async
    def get_historial_ia(self, conv_id):
        from .models import Mensaje
        mensajes = Mensaje.objects.filter(
            conversacion_id=conv_id,
            origen__in=['cliente', 'ia']
        ).order_by('enviado')
        historial = []
        for m in mensajes:
            role = 'user' if m.origen == 'cliente' else 'assistant'
            historial.append({'role': role, 'content': m.texto})
        return historial

    @database_sync_to_async
    def asignar_agente(self, conv_id, user):
        from .models import Conversacion
        Conversacion.objects.filter(pk=conv_id).update(
            agente=user, estado='atendida', modo_ia=False
        )

    @database_sync_to_async
    def toggle_ia(self, conv_id, activo):
        from .models import Conversacion
        Conversacion.objects.filter(pk=conv_id).update(modo_ia=activo)

    @database_sync_to_async
    def cerrar_conversacion(self, conv_id):
        from .models import Conversacion
        Conversacion.objects.filter(pk=conv_id).update(
            estado='cerrada', cerrada=timezone.now()
        )
