import asyncio
from collections import defaultdict


class PresenceRegistry:
    """Process-local registry: valid for the prototype's single Daphne process."""

    def __init__(self):
        self._students = defaultdict(lambda: defaultdict(set))
        self._lock = asyncio.Lock()

    async def add(self, exam_id, student_id, connection_id):
        async with self._lock:
            self._students[str(exam_id)][str(student_id)].add(connection_id)
            return len(self._students[str(exam_id)])

    async def remove(self, exam_id, student_id, connection_id):
        async with self._lock:
            connections = self._students[str(exam_id)].get(str(student_id))
            if connections:
                connections.discard(connection_id)
                if not connections:
                    self._students[str(exam_id)].pop(str(student_id), None)
            return len(self._students[str(exam_id)])

    async def count(self, exam_id):
        async with self._lock:
            # Consulta de sólo lectura: no se usa el acceso por corchetes para
            # que el defaultdict no cree una entrada por cada examen consultado.
            return len(self._students.get(str(exam_id), ()))


presence_registry = PresenceRegistry()
