import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.serializers.json import DjangoJSONEncoder

from .models import Activity, QuizAttempt
from .presence import presence_registry
from .serializers import QuizAttemptSerializer

logger = logging.getLogger(__name__)


class ActivityConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.activity_id = self.scope["url_route"]["kwargs"]["activity_id"]
        params = parse_qs(self.scope.get("query_string", b"").decode())
        self.role = params.get("role", ["student"])[0]
        self.attempt_id = params.get("attempt_id", [None])[0]

        if not await self._activity_exists():
            await self.close(code=4404)
            return
        if self.role == "student" and not self.attempt_id:
            await self.close(code=4400)
            return

        self.group_name = f"activity_{self.activity_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        self.staff_group_name = f"activity_staff_{self.activity_id}" if self.role != "student" else None
        if self.staff_group_name:
            await self.channel_layer.group_add(self.staff_group_name, self.channel_name)
        await self.accept()

        identity = self.attempt_id if self.role == "student" else None
        count = (
            await presence_registry.add(self.activity_id, identity, self.channel_name)
            if self.role == "student"
            else await presence_registry.count(self.activity_id)
        )
        await self.send_json({"type": "presence_changed", "connected_students": count})
        await self._broadcast_presence(count, exclude_channel=self.channel_name)
        await self.send_json({"type": "activity_state", "activity_id": self.activity_id, "status": "activa"})

        if self.role == "student":
            attempt = await self._get_attempt()
            if attempt:
                await self.channel_layer.group_send(
                    f"activity_staff_{self.activity_id}",
                    {"type": "activity.event", "payload": {"type": "student_progress", "activity_id": self.activity_id, "attempt": attempt}},
                )
        logger.info("websocket_connected activity=%s role=%s attempt=%s", self.activity_id, self.role, self.attempt_id)

    async def disconnect(self, close_code):
        if not hasattr(self, "group_name"):
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if self.staff_group_name:
            await self.channel_layer.group_discard(self.staff_group_name, self.channel_name)
        if self.role == "student":
            count = await presence_registry.remove(self.activity_id, self.attempt_id, self.channel_name)
            await self._broadcast_presence(count)
        logger.info("websocket_disconnected activity=%s role=%s attempt=%s code=%s", self.activity_id, self.role, self.attempt_id, close_code)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            message = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send_json({"type": "error", "message": "JSON inválido"})
            return
        if message.get("type") in ("ping", "heartbeat"):
            await self.send_json({"type": "pong"})

    async def activity_event(self, event):
        await self.send_json(event["payload"])

    async def presence_event(self, event):
        if event.get("exclude_channel") == self.channel_name:
            return
        await self.send_json(event["payload"])

    async def _broadcast_presence(self, count, exclude_channel=None):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "presence.event",
                "payload": {"type": "presence_changed", "connected_students": count},
                "exclude_channel": exclude_channel,
            },
        )

    @database_sync_to_async
    def _activity_exists(self):
        return Activity.objects.filter(pk=self.activity_id, activity_type="quiz").exists()

    @database_sync_to_async
    def _get_attempt(self):
        attempt = QuizAttempt.objects.select_related("actividad").prefetch_related("respuestas").filter(
            pk=self.attempt_id, actividad_id=self.activity_id
        ).first()
        return QuizAttemptSerializer(attempt).data if attempt else None

    async def send_json(self, payload):
        # DRF conserva puntaje/max_score como números; DjangoJSONEncoder permite
        # emitir Decimal por Channels sin cerrar el socket del profesor.
        await self.send(text_data=json.dumps(payload, cls=DjangoJSONEncoder))
