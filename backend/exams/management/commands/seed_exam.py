from decimal import Decimal

from django.core.management.base import BaseCommand

from exams.catalog import activate_version
from exams.models import (
    Activity,
    Course,
    CourseEnrollment,
    CourseVersion,
    CurriculumFramework,
    LearningResource,
    Lesson,
    LessonItem,
    QuizAnswer,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    Section,
    now_ms,
)


COURSE_TITLE = "Álgebra Octavo B"
QUIZ_TITLE = "Quiz de cultura general sobre México"

QUESTIONS = [
    (
        "Deporte",
        "¿Qué futbolista mexicano fue reconocido como uno de los máximos goleadores del Real Madrid durante la década de 1980?",
        ["Rafael Márquez", "Cuauhtémoc Blanco", "Hugo Sánchez", "Jorge Campos"],
        2,
    ),
    (
        "Ciencia",
        "¿Qué científico mexicano recibió el Premio Nobel de Química en 1995 por sus investigaciones sobre el deterioro de la capa de ozono?",
        ["Mario Molina", "Luis Ernesto Miramontes", "Manuel Sandoval Vallarta", "Guillermo González Camarena"],
        0,
    ),
    (
        "Ciencia",
        "¿Qué científico mexicano participó en la síntesis de la noretisterona, compuesto fundamental para el desarrollo de la píldora anticonceptiva?",
        ["Alfonso Caso", "Luis Ernesto Miramontes", "Mario Molina", "Carlos de Sigüenza y Góngora"],
        1,
    ),
    (
        "Historia",
        "¿En qué año comenzó oficialmente la Guerra de Independencia de México?",
        ["1810", "1821", "1910", "1847"],
        0,
    ),
    (
        "Geografía",
        "¿Cuál es el estado más grande de México por extensión territorial?",
        ["Sonora", "Coahuila", "Durango", "Chihuahua"],
        3,
    ),
]


class Command(BaseCommand):
    help = "Crea Álgebra Octavo B, su estructura, el quiz de México y resultados demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Regenera solamente los registros del curso demo.",
        )

    def handle(self, *args, **options):
        self._frameworks()
        if options["recreate"]:
            self._borrar_curso_demo()
            Activity.objects.filter(titulo=QUIZ_TITLE).delete()
            LearningResource.objects.filter(content_ref__startswith="avacom:algebra8b/").delete()

        if Course.objects.filter(titulo=COURSE_TITLE).exists():
            course = Course.objects.get(titulo=COURSE_TITLE)
            self.stdout.write(self.style.WARNING(f"El curso demo ya existe (id={course.id}); no se duplicó."))
            return

        # Nace en BORRADOR. Se habilita al activar su primera versión: el CHECK
        # ck_m05_curso_habilitado_con_version rechaza un curso habilitado que no
        # apunte a ninguna fotografía.
        course = Course.objects.create(
            titulo=COURSE_TITLE,
            descripcion="Curso demostrativo para explorar expresiones algebraicas, ecuaciones y una actividad final en vivo.",
            docente_id="docente-demo",
            curriculum_framework_id="SEP_MX",
            estado=Course.ESTADO_BORRADOR,
            creado_por="docente-demo",
        )
        version_one = CourseVersion.objects.create(
            curso=course,
            version=1,
            package_version="1.0.0",
            estado=CourseVersion.ESTADO_INSTALADA,
            instalada_por="docente-demo",
            huella="e31f9b9b1d1f4341af5b6b5b4206465c19ef938e6f7bcabfbd5fa91bed3b3cc2",
            notas="Versión demo con dos secciones, tres lecciones y quiz final.",
            creado_por="docente-demo",
        )

        for persona_id in ("sofia-ramirez", "mateo-garcia", "valentina-lopez"):
            CourseEnrollment.objects.create(curso=course, persona_id=persona_id, creado_por="docente-demo")

        # Las secciones cuelgan de la VERSIÓN, no del curso.
        section_one = Section.objects.create(
            curso_version=version_one, codigo="section.fundamentos", titulo="Fundamentos del álgebra",
            orden=1, creado_por="docente-demo",
        )
        section_two = Section.objects.create(
            curso_version=version_one, codigo="section.ecuaciones", titulo="Ecuaciones y aplicación",
            orden=2, creado_por="docente-demo",
        )

        lesson_one = self._lesson(
            section_one,
            1,
            "Lenguaje algebraico",
            "Traduce situaciones cotidianas a expresiones con variables y constantes.",
            "Representa relaciones sencillas mediante expresiones algebraicas.",
        )
        lesson_two = self._lesson(
            section_one,
            2,
            "Expresiones y términos semejantes",
            "Identifica coeficientes, variables y términos semejantes para simplificar expresiones.",
            "Reduce expresiones algebraicas combinando términos semejantes.",
        )
        lesson_three = self._lesson(
            section_two,
            1,
            "Ecuaciones de primer grado",
            "Resuelve ecuaciones lineales y comprueba la solución por sustitución.",
            "Modela y resuelve problemas con una ecuación de primer grado.",
        )

        resources = [
            LearningResource.objects.create(
                titulo="Lectura · Variables y constantes",
                content_type="reading",
                content_ref="avacom:algebra8b/lectura-variables",
                content_version="1.0",
                autor_id="docente-demo",
                creado_por="docente-demo",
            ),
            LearningResource.objects.create(
                titulo="Video · Simplificar expresiones",
                content_type="video",
                content_ref="avacom:algebra8b/video-terminos-semejantes",
                content_version="1.0",
                duracion_seg=360,
                autor_id="docente-demo",
                creado_por="docente-demo",
            ),
            LearningResource.objects.create(
                titulo="Lectura · Equilibrio en una ecuación",
                content_type="reading",
                content_ref="avacom:algebra8b/lectura-ecuaciones",
                content_version="1.0",
                autor_id="docente-demo",
                creado_por="docente-demo",
            ),
        ]

        LessonItem.objects.create(leccion=lesson_one, orden=1, tipo="contenido", recurso=resources[0], creado_por="docente-demo")
        LessonItem.objects.create(
            leccion=lesson_one,
            orden=2,
            tipo="referencia_externa",
            elemento_ref="avacom:algebra8b/practica/lenguaje-algebraico",
            elemento_version="1.0",
            creado_por="docente-demo",
        )
        LessonItem.objects.create(leccion=lesson_two, orden=1, tipo="contenido", recurso=resources[1], creado_por="docente-demo")
        LessonItem.objects.create(
            leccion=lesson_two,
            orden=2,
            tipo="referencia_externa",
            elemento_ref="avacom:algebra8b/practica/terminos-semejantes",
            elemento_version="1.0",
            creado_por="docente-demo",
        )
        LessonItem.objects.create(leccion=lesson_three, orden=1, tipo="contenido", recurso=resources[2], creado_por="docente-demo")

        activity = Activity.objects.create(
            activity_ref="avacom:algebra8b/quiz-cultura-mexico",
            titulo=QUIZ_TITLE,
            descripcion="Cinco preguntas de deporte, ciencia, historia y geografía de México.",
            activity_type="quiz",
            submission_type="quiz",
            grading_type="automatic",
            max_score=100,
            autor_id="docente-demo",
            creado_por="docente-demo",
        )
        LessonItem.objects.create(leccion=lesson_three, orden=2, tipo="actividad", actividad=activity, creado_por="docente-demo")

        created_questions = []
        for order, (category, text, options_list, correct_index) in enumerate(QUESTIONS, start=1):
            question = QuizQuestion.objects.create(actividad=activity, categoria=category, texto=text, orden=order)
            options = [
                QuizOption.objects.create(
                    pregunta=question,
                    texto=option_text,
                    orden=option_order,
                    es_correcta=(option_order - 1 == correct_index),
                )
                for option_order, option_text in enumerate(options_list, start=1)
            ]
            created_questions.append((question, options, correct_index))

        self._attempt(activity, "sofia-ramirez", "Sofía Ramírez", created_questions, [True] * 5, finished=True)
        self._attempt(activity, "mateo-garcia", "Mateo García", created_questions, [True, True, False, True, True], finished=True)
        self._attempt(activity, "valentina-lopez", "Valentina López", created_questions[:2], [True, True], finished=False)

        # Recién ahora se publica: la fotografía ya está completa. Esto mueve el
        # puntero y pasa el curso a 'habilitado', además de dejar la traza en
        # m19_auditoria. Es el mismo camino que usa la API.
        activate_version(version_one.pk, actor="docente-demo")
        course.refresh_from_db()

        self.stdout.write(
            self.style.SUCCESS(
                f"Curso «{COURSE_TITLE}» creado con 2 secciones, 3 lecciones, 6 ítems y quiz de 5 preguntas "
                f"(id={course.id}, versión activa={course.version_activa_id})."
            )
        )

    @staticmethod
    def _borrar_curso_demo():
        """
        Borra el curso demo respetando PROTECT: de las hojas hacia la raíz.

        El modelo no lleva ON DELETE CASCADE a propósito —un borrado accidental
        no debe llevarse historial académico por delante—, así que aquí el orden
        es explícito y queda a la vista lo que se está destruyendo.
        """
        cursos = list(Course.objects.filter(titulo=COURSE_TITLE))
        if not cursos:
            return
        for curso in cursos:
            # 1) soltar el puntero para poder borrar las versiones
            Course.objects.filter(pk=curso.pk).update(
                version_activa=None, estado=Course.ESTADO_BORRADOR
            )
            versiones = CourseVersion.objects.filter(curso=curso)
            LessonItem.objects.filter(leccion__seccion__curso_version__in=versiones).delete()
            Lesson.objects.filter(seccion__curso_version__in=versiones).delete()
            Section.objects.filter(curso_version__in=versiones).delete()
            CourseEnrollment.objects.filter(curso=curso).delete()
            versiones.delete()
        Course.objects.filter(titulo=COURSE_TITLE).delete()

    @staticmethod
    def _frameworks():
        for key, name, country, order in [
            ("MEN_CO", "MEN Colombia", "CO", 1),
            ("SEP_MX", "SEP México", "MX", 2),
            ("LOMLOE_ES", "LOMLOE España", "ES", 3),
            ("OECD_LC", "OECD Learning Compass", None, 4),
            ("OTRO", "Otro", None, 9),
        ]:
            CurriculumFramework.objects.update_or_create(
                clave=key,
                defaults={"nombre": name, "pais": country, "orden": order, "activo": True},
            )

    @staticmethod
    def _lesson(section, order, title, description, outcome, codigo=None):
        return Lesson.objects.create(
            seccion=section,
            # Identidad lógica, estable entre versiones. El id es la física.
            codigo=codigo or f"lesson.{section.codigo.split('.', 1)[-1]}-{order}",
            titulo=title,
            descripcion=description,
            competency_framework="PDA_MX",
            learning_outcome=outcome,
            skills="Modelar · Resolver · Explicar el procedimiento",
            attitudes_values="Curiosidad, perseverancia y colaboración.",
            orden=order,
            estado=Lesson.ESTADO_PUBLICADO,
            creado_por="docente-demo",
        )

    @staticmethod
    def _attempt(activity, person_id, name, questions, correctness, finished):
        attempt = QuizAttempt.objects.create(
            actividad=activity,
            persona_id=person_id,
            nombre_estudiante=name,
            device_id=f"demo-{person_id}",
            estado=QuizAttempt.ESTADO_FINALIZADO if finished else QuizAttempt.ESTADO_EN_PROGRESO,
            pregunta_actual=5 if finished else 3,
            puntaje=Decimal(sum(correctness) * 20) if finished else 0,
            total_preguntas=5,
            finalizado_en=now_ms() if finished else None,
        )
        for (question, options, correct_index), is_correct in zip(questions, correctness):
            selected = options[correct_index] if is_correct else options[(correct_index + 1) % len(options)]
            QuizAnswer.objects.create(
                intento=attempt,
                pregunta=question,
                opcion=selected,
                es_correcta=selected.es_correcta,
            )
