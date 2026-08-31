"""
Catálogo de curso VERSIONADO · los 6 cambios del modelo entregado.

La idea en una frase:
    m05_curso              es la IDENTIDAD permanente del curso
    m05_curso_version      es una FOTOGRAFÍA inmutable de su contenido
    m05_curso.version_activa_id  es un puntero a la fotografía publicada

Publicar contenido nuevo = escribir una fotografía nueva y mover el puntero.
Rollback = mover el puntero al revés. Ninguna de las dos borra ni edita nada.

Esta migración está escrita A MANO y no autogenerada, porque hay que intercalar
en un orden preciso: añadir columnas nulables -> rellenarlas con los datos que
ya existen -> recién entonces volverlas obligatorias y añadir las UNIQUE. El
autogenerador no puede resolver ese orden sin preguntar.

Se probó sobre la base de desarrollo con datos previos (1 curso, 2 secciones,
3 lecciones, 6 items, 3 inscripciones, y el quiz de México con 6 intentos y
23 respuestas): migra sin pérdida y es reversible.
"""

import re

from django.db import migrations, models
from django.db.models import F, Q
import django.db.models.deletion


def slug(texto, prefijo):
    """Deriva un codigo lógico estable a partir de un título existente."""
    base = (texto or "").lower()
    base = base.replace("á", "a").replace("é", "e").replace("í", "i")
    base = base.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return f"{prefijo}.{base or 'sin-titulo'}"[:120]


def hacia_adelante(apps, schema_editor):
    """
    Reparte los datos existentes en el modelo versionado.

    Cada curso que ya tenía secciones colgando de él pasa a tener una V1 que las
    contiene. Si el curso ya tenía una fila en m05_curso_version se reutiliza esa
    en lugar de crear una nueva, para no inventar historial.
    """
    Course = apps.get_model("exams", "Course")
    CourseVersion = apps.get_model("exams", "CourseVersion")
    Section = apps.get_model("exams", "Section")
    Lesson = apps.get_model("exams", "Lesson")
    Activity = apps.get_model("exams", "Activity")

    # --- CAMBIO 6 · activity_ref para las actividades que ya existen ----------
    for actividad in Activity.objects.all():
        if not actividad.activity_ref:
            actividad.activity_ref = slug(actividad.titulo, "avacom:actividad")
            actividad.save(update_fields=["activity_ref"])

    # --- CAMBIOS 1, 2 y 3 · versión, puntero y secciones repuntadas ----------
    for curso in Course.objects.all():
        version = (
            CourseVersion.objects.filter(curso=curso).order_by("version").first()
        )
        if version is None:
            version = CourseVersion.objects.create(
                curso=curso,
                version=1,
                instalada_por=curso.creado_por or curso.docente_id or "migracion",
                huella="0" * 64,
                notas="Versión 1 derivada del contenido que existía antes del modelo versionado.",
                creado_por="migracion-0004",
            )

        # La V1 derivada queda ACTIVA si el curso estaba habilitado; si estaba en
        # borrador queda instalada y sin publicar, que es lo coherente.
        estaba_publicado = curso.estado == "habilitado"
        version.package_version = version.package_version or "1.0.0"
        version.estado = "activa" if estaba_publicado else "instalada"
        version.activada_en = version.instalada_en if estaba_publicado else None
        version.save(update_fields=["package_version", "estado", "activada_en"])

        # Las secciones del curso pasan a colgar de la versión.
        Section.objects.filter(curso_id=curso.id).update(curso_version=version)

        if estaba_publicado:
            curso.version_activa = version
            curso.save(update_fields=["version_activa"])

    # --- CAMBIO 4 · codigo lógico en secciones y lecciones -------------------
    for seccion in Section.objects.all():
        if not seccion.codigo:
            seccion.codigo = slug(seccion.titulo, "section")
            seccion.save(update_fields=["codigo"])

    for leccion in Lesson.objects.all():
        if not leccion.codigo:
            leccion.codigo = slug(leccion.titulo, "lesson")
            leccion.save(update_fields=["codigo"])

    # Los codigos derivados de títulos pueden chocar dentro de una misma
    # sección o versión. Se desempatan con el orden, que ya es único.
    _desempatar(Section, "curso_version_id")
    _desempatar(Lesson, "seccion_id")


def _desempatar(modelo, campo_padre):
    vistos = {}
    for fila in modelo.objects.all().order_by(campo_padre, "orden"):
        clave = (getattr(fila, campo_padre), fila.codigo)
        if clave in vistos:
            fila.codigo = f"{fila.codigo}-{fila.orden}"[:120]
            fila.save(update_fields=["codigo"])
        else:
            vistos[clave] = fila.pk


def hacia_atras(apps, schema_editor):
    """
    Vuelta atrás: las secciones regresan a colgar del curso.

    Se usa la versión ACTIVA de cada curso como origen. El historial de las
    versiones no activas no tiene dónde ir en el modelo viejo, así que sus
    secciones se quedarían huérfanas: se rechaza el reverso si existe más de una
    versión con contenido, en lugar de perder datos en silencio.
    """
    Course = apps.get_model("exams", "Course")
    Section = apps.get_model("exams", "Section")

    for curso in Course.objects.all():
        con_contenido = {
            s.curso_version_id for s in Section.objects.filter(curso_version__curso=curso)
        }
        if len(con_contenido) > 1:
            raise RuntimeError(
                f"El curso {curso.id} tiene contenido en {len(con_contenido)} versiones. "
                "Revertir esta migración perdería el historial: consolida a una sola "
                "versión antes de bajar de la 0004."
            )
        for seccion in Section.objects.filter(curso_version__curso=curso):
            seccion.curso_id = curso.id
            seccion.save(update_fields=["curso_id"])


class Migration(migrations.Migration):

    dependencies = [("exams", "0003_alter_activity_max_score")]

    operations = [
        # ── PASO 1 · columnas nuevas, todas nulables por ahora ───────────────
        migrations.RenameField("courseversion", "publicado_en", "instalada_en"),
        migrations.RenameField("courseversion", "publicado_por", "instalada_por"),
        migrations.AddField(
            "courseversion",
            "estado",
            models.CharField(
                choices=[
                    ("staged", "Staged"),
                    ("instalada", "Instalada"),
                    ("activa", "Activa"),
                    ("retirada", "Retirada"),
                    ("error", "Error"),
                ],
                default="staged",
                max_length=16,
            ),
        ),
        migrations.AddField(
            "courseversion", "package_version",
            models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            "courseversion", "activada_en", models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            "courseversion", "retirada_en", models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            "course",
            "version_activa",
            models.ForeignKey(
                blank=True, db_column="version_activa_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+", to="exams.courseversion",
            ),
        ),
        migrations.AddField(
            "section",
            "curso_version",
            models.ForeignKey(
                db_column="curso_version_id", null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="secciones", to="exams.courseversion",
            ),
        ),
        migrations.AddField("section", "codigo", models.CharField(default="", max_length=120)),
        migrations.AddField("lesson", "codigo", models.CharField(default="", max_length=120)),
        migrations.AddField("activity", "activity_ref", models.CharField(default="", max_length=500)),

        # Las UNIQUE viejas se quitan antes de repuntar, porque están definidas
        # sobre (curso, orden) y esa columna está a punto de desaparecer.
        migrations.RemoveConstraint("section", "ux_m05_seccion_orden"),
        migrations.RemoveIndex("learningresource", "ix_m05_recurso_ref"),

        # ── PASO 2 · repartir los datos que ya existen ───────────────────────
        migrations.RunPython(hacia_adelante, hacia_atras),

        # ── PASO 3 · ahora sí, obligatorias y sin la columna vieja ───────────
        migrations.AlterField(
            "section",
            "curso_version",
            models.ForeignKey(
                db_column="curso_version_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="secciones", to="exams.courseversion",
            ),
        ),
        migrations.RemoveField("section", "curso"),
        # CAMBIO 2 · el entero se elimina: se desincroniza del contenido.
        migrations.RemoveField("course", "version"),

        # ── PASO 4 · el resto de on_delete de la cadena del catálogo ─────────
        migrations.AlterField(
            "courseversion", "curso",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="versiones", to="exams.course",
            ),
        ),
        migrations.AlterField(
            "courseenrollment", "curso",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="inscripciones", to="exams.course",
            ),
        ),
        migrations.AlterField(
            "lesson", "seccion",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lecciones", to="exams.section",
            ),
        ),
        migrations.AlterField(
            "lessonitem", "leccion",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="items", to="exams.lesson",
            ),
        ),

        # ── PASO 5 · la integridad, en el motor y no en la aplicación ────────
        migrations.AddIndex(
            "courseversion",
            models.Index(fields=["estado", "curso"], name="ix_m05_cv_estado"),
        ),
        migrations.AddConstraint(
            "courseversion",
            models.UniqueConstraint(
                fields=["curso"], condition=Q(estado="activa"), name="ux_m05_cv_una_activa",
            ),
        ),
        migrations.AddConstraint(
            "courseversion",
            models.CheckConstraint(
                condition=Q(activada_en__isnull=True) | Q(activada_en__gte=F("instalada_en")),
                name="ck_m05_cv_activada_tras_instalada",
            ),
        ),
        migrations.AddConstraint(
            "courseversion",
            models.CheckConstraint(
                condition=Q(retirada_en__isnull=True) | Q(retirada_en__gte=F("instalada_en")),
                name="ck_m05_cv_retirada_tras_instalada",
            ),
        ),
        migrations.AddConstraint(
            "courseversion",
            models.CheckConstraint(
                condition=~Q(estado="activa") | Q(activada_en__isnull=False),
                name="ck_m05_cv_activa_con_fecha",
            ),
        ),
        migrations.AddConstraint(
            "courseversion",
            models.CheckConstraint(
                condition=~Q(estado="retirada") | Q(retirada_en__isnull=False),
                name="ck_m05_cv_retirada_con_fecha",
            ),
        ),
        migrations.AddConstraint(
            "course",
            models.CheckConstraint(
                condition=Q(estado__in=["borrador", "pruebas", "retirado"])
                | Q(version_activa__isnull=False),
                name="ck_m05_curso_habilitado_con_version",
            ),
        ),
        migrations.AddConstraint(
            "section",
            models.UniqueConstraint(fields=["curso_version", "orden"], name="ux_m05_seccion_orden"),
        ),
        migrations.AddConstraint(
            "section",
            models.UniqueConstraint(fields=["curso_version", "codigo"], name="ux_m05_seccion_codigo"),
        ),
        migrations.AddConstraint(
            "lesson",
            models.UniqueConstraint(fields=["seccion", "codigo"], name="ux_m05_leccion_codigo"),
        ),
        migrations.AddConstraint(
            "learningresource",
            models.UniqueConstraint(
                fields=["content_ref", "content_version"], name="ux_m05_recurso_ref"
            ),
        ),
        migrations.AddConstraint(
            "activity",
            models.UniqueConstraint(fields=["activity_ref", "version"], name="ux_m10_actividad_ref"),
        ),

        # ── PASO 6 · retirar los default="" ──────────────────────────────────
        # El default solo existía para poder añadir columnas obligatorias sobre
        # filas que ya estaban. Una vez rellenadas en el paso 2, sobra: un
        # codigo vacío no debe poder colarse por omisión.
        migrations.AlterField("section", "codigo", models.CharField(max_length=120)),
        migrations.AlterField("lesson", "codigo", models.CharField(max_length=120)),
        migrations.AlterField("activity", "activity_ref", models.CharField(max_length=500)),
    ]
