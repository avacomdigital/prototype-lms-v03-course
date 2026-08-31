"""
m05_curso_host deja de estar acoplada a SCORM y admite también CMI5.

Sale:
    scorm_manifest_id, scorm_organization_id, scorm_version
Entra:
    formato_contenido, package_identifier, package_version,
    manifest_tipo, manifest_ref

SCORM y CMI5 pasan a ser formatos de ENTRADA, no modelos distintos de curso:
cada parser transforma su paquete al mismo árbol
    curso -> sección -> lección -> lesson item

    SCORM 2004   formato=scorm_2004  manifest_tipo=imsmanifest  ref=imsmanifest.xml
    CMI5         formato=cmi5        manifest_tipo=cmi5         ref=cmi5.xml
    nativo       formato=avacom_v1   manifest_tipo=avacom       ref=<paquete>.json

También cambia la clave de unicidad, de (host, curso) a (host, curso, versión),
para conservar el historial de QUÉ versión estuvo instalada en cada host. Ese
cambio abre dos huecos que se tapan con índices únicos PARCIALES; ver los
comentarios de las constraints al final.

Escrita a mano y no autogenerada: hay que rellenar formato_contenido a partir de
las columnas SCORM ANTES de borrarlas, y el autodetector lo interpreta como un
renombre.
"""

from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def hacia_adelante(apps, schema_editor):
    """
    Deduce el formato de las filas que ya existen.

    Si la fila traía un manifest SCORM, era SCORM. Si no, venía por el camino
    nativo del prototipo, que es el único implementado hoy.
    """
    CourseHost = apps.get_model("exams", "CourseHost")
    for fila in CourseHost.objects.all():
        if fila.scorm_manifest_id:
            fila.formato_contenido = "scorm_2004"
            fila.manifest_tipo = "imsmanifest"
            fila.manifest_ref = "imsmanifest.xml"
            fila.package_identifier = fila.scorm_manifest_id
            # scorm_version guardaba '2004-4ED': eso describe el formato, que ya
            # quedó en formato_contenido, así que no se arrastra a package_version.
        else:
            fila.formato_contenido = "avacom_v1"
            fila.manifest_tipo = "avacom"
        fila.save(update_fields=[
            "formato_contenido", "manifest_tipo", "manifest_ref", "package_identifier",
        ])


def hacia_atras(apps, schema_editor):
    """
    Vuelta atrás: solo lo que SCORM puede representar.

    Una fila CMI5 no tiene equivalente en las columnas scorm_*, así que se
    rechaza el reverso en lugar de perder su procedencia en silencio.
    """
    CourseHost = apps.get_model("exams", "CourseHost")
    cmi5 = CourseHost.objects.filter(formato_contenido="cmi5").count()
    if cmi5:
        raise RuntimeError(
            f"Hay {cmi5} fila(s) en formato cmi5. Las columnas scorm_* del modelo "
            "anterior no pueden representarlas: revertir esta migración perdería su "
            "procedencia. Reinstala esos paquetes como SCORM antes de bajar de la 0006."
        )
    for fila in CourseHost.objects.all():
        if fila.formato_contenido in ("scorm_12", "scorm_2004"):
            fila.scorm_manifest_id = fila.package_identifier
            fila.scorm_version = "2004-4ED" if fila.formato_contenido == "scorm_2004" else "1.2"
            fila.save(update_fields=["scorm_manifest_id", "scorm_version"])


FORMATOS = [
    ("scorm_12", "SCORM 1.2"),
    ("scorm_2004", "SCORM 2004"),
    ("cmi5", "cmi5"),
    ("avacom_v1", "AVACOM course package v1"),
]


class Migration(migrations.Migration):

    dependencies = [("exams", "0005_curso_host")]

    operations = [
        # ── PASO 1 · columnas nuevas ─────────────────────────────────────────
        migrations.AddField(
            "coursehost", "formato_contenido",
            models.CharField(choices=FORMATOS, default="avacom_v1", max_length=16),
        ),
        migrations.AddField(
            "coursehost", "package_identifier",
            models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            "coursehost", "package_version",
            models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            "coursehost", "manifest_tipo",
            models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            "coursehost", "manifest_ref",
            models.CharField(blank=True, max_length=500, null=True),
        ),

        # ── PASO 2 · deducir el formato de lo que ya está instalado ──────────
        migrations.RunPython(hacia_adelante, hacia_atras),

        # ── PASO 3 · fuera las columnas atadas a SCORM ──────────────────────
        migrations.RemoveField("coursehost", "scorm_manifest_id"),
        migrations.RemoveField("coursehost", "scorm_organization_id"),
        migrations.RemoveField("coursehost", "scorm_version"),

        # ── PASO 4 · la clave de unicidad pasa a incluir la versión ──────────
        # Con (host, curso) se perdía el rastro de qué versión estuvo instalada:
        # al instalar V2 sobre V1 se sobrescribía curso_version_id.
        migrations.RemoveConstraint("coursehost", "ux_m05_ch_host_curso"),
        migrations.AddConstraint(
            "coursehost",
            models.UniqueConstraint(
                fields=["host_id", "curso", "curso_version"],
                name="ux_m05_ch_host_curso_version",
            ),
        ),

        # Hueco 1 · un UNIQUE trata dos NULL como distintos, tanto en SQLite como
        # en Postgres. Sin esto, (host, curso, NULL) se podría insertar tantas
        # veces como se quiera y se rompería la idempotencia de register_install().
        migrations.AddConstraint(
            "coursehost",
            models.UniqueConstraint(
                fields=["host_id", "curso"],
                condition=Q(curso_version__isnull=True),
                name="ux_m05_ch_sin_version",
            ),
        ),

        # Hueco 2 · con filas por versión, dos versiones del mismo curso podrían
        # quedar ofrecidas a la vez en el mismo host y el estudiante vería el
        # curso duplicado. Mismo idiom que ux_m05_cv_una_activa.
        migrations.AddConstraint(
            "coursehost",
            models.UniqueConstraint(
                fields=["host_id", "curso"],
                condition=Q(disponible_estudiante=True),
                name="ux_m05_ch_una_disponible",
            ),
        ),

        migrations.AddIndex(
            "coursehost",
            models.Index(fields=["formato_contenido"], name="ix_m05_ch_formato"),
        ),
    ]
