"""Prueba end-to-end del prototipo de cursos AVACOM.

Con la API ya iniciada:

    python backend/tools/endpoint_proof.py --base-url http://127.0.0.1:8000

Valida el catálogo anidado, un CRUD pequeño, inscripción, quiz, calificación y
la difusión WebSocket de la pregunta actual hacia OPS Master. Crea un intento
de prueba nuevo; el curso CRUD temporal se elimina al terminar.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


checks: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: object = "") -> bool:
    checks.append((ok, label))
    mark = "OK   " if ok else "FALLA"
    print(f"  {mark} {label}" + (f"  ->  {detail}" if detail != "" else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{'=' * 82}\n{title}\n{'=' * 82}")


class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def call(self, method: str, path: str, body: object | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            try:
                return error.code, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return error.code, raw
        except urllib.error.URLError as error:
            raise SystemExit(
                f"No se pudo alcanzar {self.base}: {error.reason}\n"
                "Verifica que OPS Master esté abierto y que el firewall permita TCP/8000."
            )

    def expect(self, method: str, path: str, body: object | None, status: int, label: str):
        code, payload = self.call(method, path, body)
        check(code == status, label, f"HTTP {code} (esperado {status})")
        return payload


def find_demo_course(courses: list[dict]) -> dict:
    for course in courses:
        if course.get("titulo") == "Álgebra Octavo B":
            return course
    raise SystemExit("No existe el curso demo. Ejecuta: python manage.py seed_exam")


def find_quiz(course: dict) -> dict:
    for course_section in course.get("secciones", []):
        for lesson in course_section.get("lecciones", []):
            for item in lesson.get("items", []):
                activity = item.get("actividad")
                if activity and activity.get("activity_type") == "quiz":
                    return activity
    raise SystemExit("El curso demo no contiene un Lesson Item de tipo quiz.")


def verify_catalog_and_crud(api: Api) -> tuple[dict, dict]:
    section("1. SALUD, CURSO Y CATÁLOGO ANIDADO")
    health = api.expect("GET", "/health/", None, 200, "la API responde en /health/")
    check(health.get("status") == "ok", "el diagnóstico reporta estado ok")

    courses = api.expect("GET", "/api/courses/?student=1", None, 200, "Student obtiene cursos habilitados")
    course = find_demo_course(courses)
    sections = course.get("secciones", [])
    lessons = [lesson for item in sections for lesson in item.get("lecciones", [])]
    lesson_items = [lesson_item for lesson in lessons for lesson_item in lesson.get("items", [])]
    check(len(sections) == 2, "Álgebra Octavo B tiene 2 secciones", len(sections))
    check(len(lessons) == 3, "el curso tiene 3 lecciones", len(lessons))
    check(len(lesson_items) == 6, "cada lección aporta 2 Lesson Items", len(lesson_items))

    quiz = find_quiz(course)
    questions = quiz.get("preguntas", [])
    check(len(questions) == 5, "el quiz de México contiene 5 preguntas", len(questions))
    check(all(len(question.get("opciones", [])) == 4 for question in questions), "cada pregunta contiene 4 opciones")
    check(
        all("es_correcta" not in option for question in questions for option in question.get("opciones", [])),
        "el contrato público no expone respuestas correctas",
    )

    section("2. CRUD NATIVO CON APIVIEWS")
    frameworks = api.expect("GET", "/api/curriculum-frameworks/", None, 200, "lista marcos curriculares")
    framework = frameworks[0]["clave"]
    suffix = str(int(time.time() * 1000))
    created = api.expect(
        "POST",
        "/api/courses/",
        {
            "titulo": f"Curso PoC {suffix}",
            "descripcion": "Registro temporal de endpoint_proof.py",
            "docente_id": "poc-docente",
            "curriculum_framework": framework,
            "estado": "borrador",
            "idioma": "es",
        },
        201,
        "POST crea un curso",
    )
    course_id = created["id"]
    patched = api.expect(
        "PATCH",
        f"/api/courses/{course_id}/",
        {"estado": "pruebas"},
        200,
        "PATCH actualiza su estado",
    )
    check(patched.get("estado") == "pruebas", "el cambio persiste")
    api.expect("DELETE", f"/api/courses/{course_id}/", None, 204, "DELETE elimina el curso temporal")
    api.expect("GET", f"/api/courses/{course_id}/", None, 404, "el curso eliminado ya no existe")

    section("3. INSCRIPCIÓN Y APERTURA DEL QUIZ")
    student_name = f"PoC Estudiante {suffix[-6:]}"
    enrollment = api.expect(
        "POST",
        "/api/enrollments/",
        {"curso": course["id"], "persona_id": student_name, "estado": "activa", "creado_por": "endpoint-proof"},
        201,
        "OPS Master asigna un estudiante al curso",
    )
    check(enrollment.get("curso") == course["id"], "la inscripción queda ligada a Álgebra Octavo B")

    public_quiz = api.expect("GET", f"/api/quizzes/{quiz['id']}/", None, 200, "Student abre la actividad final")
    attempt = api.expect(
        "POST",
        "/api/quiz-attempts/start/",
        {
            "actividad_id": quiz["id"],
            "nombre_estudiante": student_name,
            "persona_id": enrollment["persona_id"],
            "device_id": f"poc-{suffix}",
        },
        201,
        "Student inicia un intento",
    )
    return public_quiz, attempt


def answer_and_finish(api: Api, quiz: dict, attempt: dict) -> dict:
    section("5. RESPUESTAS, NOTA Y CONSOLIDADO")
    questions = quiz["preguntas"]
    for position, question in enumerate(questions, start=1):
        api.expect(
            "POST",
            "/api/quiz-attempts/progress/",
            {"intento_id": attempt["id"], "pregunta_actual": position},
            200,
            f"registra avance en pregunta {position}",
        )
        api.expect(
            "POST",
            "/api/quiz-attempts/answer/",
            {
                "intento_id": attempt["id"],
                "pregunta_id": question["id"],
                "opcion_id": question["opciones"][0]["id"],
                "client_event_id": f"proof-{attempt['id']}-{position}",
            },
            201,
            f"guarda respuesta {position}",
        )

    summary = api.expect(
        "POST",
        "/api/quiz-attempts/finish/",
        {"intento_id": attempt["id"]},
        200,
        "finaliza y califica el intento",
    )
    check(summary.get("estado") == "finalizado", "el intento queda finalizado")
    check(summary.get("respondidas") == 5, "el intento registra cinco respuestas")
    check(0 <= float(summary.get("puntaje", -1)) <= 100, "la nota está en escala 0–100", summary.get("puntaje"))

    activity_id = quiz["id"]
    results = api.expect(
        "GET",
        f"/api/quiz-results/?actividad_id={urllib.parse.quote(activity_id)}",
        None,
        200,
        "OPS Master consulta el consolidado",
    )
    check(any(row["id"] == attempt["id"] for row in results), "el intento aparece en el consolidado")
    detail = api.expect("GET", f"/api/quiz-results/{attempt['id']}/", None, 200, "consulta el detalle de respuestas")
    check(len(detail.get("answers", [])) == 5, "el detalle contiene una fila por pregunta")
    return summary


async def verify_websocket(base_url: str, api: Api, quiz: dict, attempt: dict) -> None:
    try:
        import websockets
    except ImportError:
        print("\n(!) WebSocket omitido: instala backend/requirements-dev.txt para comprobarlo.")
        return

    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
    activity_id = quiz["id"]

    async def receive_until(socket, expected: str, timeout: float = 4.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            message = json.loads(await asyncio.wait_for(socket.recv(), remaining))
            if message.get("type") == expected:
                return message
        return None

    section("4. WEBSOCKET · PREGUNTA ACTUAL EN OPS MASTER")
    professor_url = f"{ws_base}/ws/activities/{activity_id}/?role=professor"
    student_url = f"{ws_base}/ws/activities/{activity_id}/?role=student&attempt_id={attempt['id']}"
    async with websockets.connect(professor_url) as professor:
        await receive_until(professor, "activity_state")
        async with websockets.connect(student_url) as student:
            connected = await receive_until(professor, "student_progress")
            check(connected is not None, "OPS recibe el intento al conectar Student")

            code, _payload = api.call(
                "POST",
                "/api/quiz-attempts/progress/",
                {"intento_id": attempt["id"], "pregunta_actual": 3},
            )
            check(code == 200, "Student publica progreso por HTTP", code)
            progress = await receive_until(professor, "student_progress")
            current = progress.get("attempt", {}).get("pregunta_actual") if progress else None
            check(current == 3, "OPS ve en vivo que el estudiante está en la pregunta 3", current)

            await student.send(json.dumps({"type": "ping"}))
            check(await receive_until(student, "pong") is not None, "el heartbeat responde pong")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-websocket", action="store_true")
    arguments = parser.parse_args()

    print(f"Prueba AVACOM Courses contra {arguments.base_url}")
    api = Api(arguments.base_url)
    quiz, attempt = verify_catalog_and_crud(api)
    if not arguments.skip_websocket:
        asyncio.run(verify_websocket(arguments.base_url, api, quiz, attempt))
    answer_and_finish(api, quiz, attempt)

    failed = [label for ok, label in checks if not ok]
    section("RESUMEN")
    print(f"  {len(checks) - len(failed)}/{len(checks)} verificaciones correctas, {len(failed)} fallas")
    for label in failed:
        print(f"    FALLA: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
