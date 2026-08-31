from exams.catalog import activate_version
from exams.models import (
    Activity,
    Course,
    CourseVersion,
    CurriculumFramework,
    Lesson,
    LessonItem,
    QuizOption,
    QuizQuestion,
    Section,
)


def make_course_version(course, version=1, package_version="1.0.0", activate=True):
    """
    Crea una fotografía y, si se pide, la publica.

    El curso NO se puede crear ya habilitado: el CHECK
    ck_m05_curso_habilitado_con_version lo rechaza si no apunta a una versión.
    Este es el orden real de la operación, y por eso las pruebas lo usan.
    """
    course_version = CourseVersion.objects.create(
        curso=course,
        version=version,
        package_version=package_version,
        estado=CourseVersion.ESTADO_INSTALADA,
        instalada_por="teacher-1",
        huella=f"{version:064d}",
    )
    if activate:
        activate_version(course_version.pk, actor="teacher-1")
        course_version.refresh_from_db()
        course.refresh_from_db()
    return course_version


def make_course(title="Álgebra de prueba", questions=2):
    framework, _ = CurriculumFramework.objects.get_or_create(
        clave="SEP_MX", defaults={"nombre": "SEP México", "pais": "MX", "orden": 1}
    )
    # Nace en borrador. Se habilita al activar su primera versión, que es lo que
    # hace activate_version(); antes de eso no hay nada que mostrar.
    course = Course.objects.create(
        titulo=title,
        descripcion="Curso de prueba",
        docente_id="teacher-1",
        curriculum_framework=framework,
        estado=Course.ESTADO_BORRADOR,
    )
    course_version = make_course_version(course)
    section = Section.objects.create(
        curso_version=course_version, codigo="section.uno", titulo="Sección 1", orden=1
    )
    lesson = Lesson.objects.create(
        seccion=section, codigo="lesson.uno", titulo="Lección 1", orden=1,
        estado=Lesson.ESTADO_PUBLICADO,
    )
    activity = Activity.objects.create(
        # activity_ref es la identidad LÓGICA y (activity_ref, version) es UNIQUE,
        # así que dos cursos en la misma prueba necesitan refs distintas.
        activity_ref=f"avacom:prueba/{course.id}/quiz-mexico",
        titulo="Quiz México",
        activity_type="quiz",
        submission_type="quiz",
        grading_type="automatic",
        max_score=100,
    )
    LessonItem.objects.create(leccion=lesson, orden=1, tipo="actividad", actividad=activity)
    for position in range(1, questions + 1):
        question = QuizQuestion.objects.create(
            actividad=activity, categoria="General", texto=f"Pregunta {position}", orden=position
        )
        for option_position in range(1, 5):
            QuizOption.objects.create(
                pregunta=question,
                texto=f"Opción {option_position}",
                orden=option_position,
                es_correcta=option_position == 1,
            )
    return course, activity


def correct_option(question):
    return question.opciones.get(es_correcta=True)


def wrong_option(question):
    return question.opciones.filter(es_correcta=False).first()
