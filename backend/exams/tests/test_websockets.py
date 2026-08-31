from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from exam_master.asgi import application
from exams.models import QuizAttempt
from exams.presence import presence_registry
from .factories import make_course


HEADERS = [(b"origin", b"http://testserver")]


class ActivityWebSocketTests(TransactionTestCase):
    def setUp(self):
        _, self.activity = make_course()
        self.attempt = QuizAttempt.objects.create(
            actividad=self.activity,
            persona_id="ada",
            nombre_estudiante="Ada",
            total_preguntas=2,
        )
        presence_registry._students.clear()

    async def connect(self, url):
        socket = WebsocketCommunicator(application, url, headers=HEADERS)
        connected, code = await socket.connect()
        self.assertTrue(connected, f"WebSocket rechazado con {code}")
        return socket

    async def read_until(self, socket, event_type, tries=8):
        for _ in range(tries):
            message = await socket.receive_json_from(timeout=3)
            if message["type"] == event_type:
                return message
        self.fail(f"No llegó {event_type}")

    async def test_student_must_send_attempt_id(self):
        socket = WebsocketCommunicator(
            application, f"/ws/activities/{self.activity.id}/?role=student", headers=HEADERS
        )
        connected, code = await socket.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4400)

    async def test_professor_receives_live_question_progress(self):
        professor = await self.connect(f"/ws/activities/{self.activity.id}/?role=professor")
        await self.read_until(professor, "presence_changed")
        await self.read_until(professor, "activity_state")
        student = await self.connect(
            f"/ws/activities/{self.activity.id}/?role=student&attempt_id={self.attempt.id}"
        )
        await self.read_until(student, "presence_changed")
        await self.read_until(student, "activity_state")
        await self.read_until(professor, "presence_changed")
        first_progress = await self.read_until(professor, "student_progress")
        self.assertEqual(first_progress["attempt"]["pregunta_actual"], 1)

        api = APIClient()
        response = await database_sync_to_async(api.post)(
            "/api/quiz-attempts/progress/",
            {"intento_id": self.attempt.id, "pregunta_actual": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        progress = await self.read_until(professor, "student_progress")
        self.assertEqual(progress["attempt"]["pregunta_actual"], 2)

        await student.disconnect()
        await professor.disconnect()
