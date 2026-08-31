"""
Exporta un SQLite limpio con SOLO las tablas del dominio, para abrirlo en DBeaver.

Por qué no basta copiar backend/db.sqlite3: esa base trae `django_migrations` y
`sqlite_sequence`, que son plomería del framework y ensucian el diagrama ER.

Qué hace de más que una copia:
  - reformatea el DDL una columna por línea (Django lo emite todo en un renglón)
  - inyecta un bloque de comentarios dentro de cada CREATE TABLE explicando su
    papel; SQLite los conserva en sqlite_master y DBeaver los muestra en la
    pestaña DDL, así que la base se documenta sola
  - conserva índices y restricciones tal como están en la base viva
  - comprueba integrity_check y foreign_key_check al final

Uso:
    python manage.py export_schema_db
    python manage.py export_schema_db --salida C:\\ruta\\modelo.db --sin-datos
"""

import os
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PREFIJOS_DOMINIO = ("m05_", "m10_", "m19_")

# Qué es cada tabla, en una frase que sirva a quien abre el diagrama sin contexto.
DESCRIPCIONES = {
    "m05_marco_curricular": [
        "MARCO CURRICULAR · catálogo de sistemas educativos.",
        "El país decide cómo se llama el elemento de competencia de una lección:",
        "CO -> DBA, MX -> PDA, ES -> Competencia, US -> Knowledge Competency.",
    ],
    "m05_curso": [
        "CURSO · la IDENTIDAD permanente. No contiene contenido.",
        "version_activa_id es un puntero a la fotografía publicada: es la ÚNICA",
        "celda que cambia al publicar o al revertir, y lo único que ve distinto",
        "el estudiante. No hay columna 'version': un entero se desincroniza del",
        "contenido, una FK no puede.",
        "CHECK: un curso habilitado tiene que estar mostrando algo.",
    ],
    "m05_curso_version": [
        "VERSIÓN · una FOTOGRAFÍA inmutable del contenido del curso.",
        "Instalar y publicar son dos momentos distintos, y por eso hay dos pares",
        "de fechas: instalada_en/por y activada_en.",
        "Una sola versión activa por curso, impuesto por el índice único PARCIAL",
        "ux_m05_cv_una_activa. Al activar hay que liberar la saliente PRIMERO.",
        "Una fotografía instalada no se edita ni se borra nunca.",
    ],
    "m05_curso_estudiante": [
        "INSCRIPCIÓN · cuelga del CURSO, no de la versión.",
        "Por eso se puede reemplazar todo el contenido sin tocar una sola fila de",
        "esta tabla, y un rollback no obliga a actualizar ninguna nota.",
    ],
    "m05_curso_host": [
        "PRESENCIA FÍSICA · ¿este curso está instalado en ESTA OPS?",
        "",
        "NEUTRAL AL ESTÁNDAR. SCORM y CMI5 son formatos de ENTRADA, no modelos",
        "distintos de curso: cada parser transforma su paquete al mismo árbol",
        "curso -> sección -> lección -> lesson item. Por eso aquí no hay columnas",
        "scorm_* ni cmi5_*, solo el formato y dónde está su descriptor:",
        "  SCORM 2004  formato=scorm_2004  manifest_tipo=imsmanifest  ref=imsmanifest.xml",
        "  CMI5        formato=cmi5        manifest_tipo=cmi5         ref=cmi5.xml",
        "  nativo      formato=avacom_v1   manifest_tipo=avacom       ref=<paquete>.json",
        "Las AU, moveOn, masteryScore y launchMethod de CMI5 NO viven aquí: esto",
        "es inventario, no runtime.",
        "No representa matrícula ni progreso: eso cuelga del curso, no del host.",
        "Dos banderas distintas a propósito:",
        "  presente_local        los archivos están en este disco",
        "  disponible_estudiante los estudiantes ya pueden usarlo",
        "Recién importado y en validación: presente=1, disponible=0.",
        "",
        "DESINSTALAR CONTENIDO no es BORRAR ENTIDADES ACADÉMICAS: al quitar el",
        "paquete se apagan las banderas y se sella retirado_en. El curso, las",
        "inscripciones, las notas y los intentos siguen intactos, y el estudiante",
        "ve «no disponible en este dispositivo» en lugar de que el curso",
        "desaparezca sin explicación.",
        "Tampoco se toca m05_curso.estado: ese es editorial, y el mismo curso",
        "puede estar habilitado y presente en Bogotá y retirado en Medellín.",
        "",
        "CHECK ck_m05_ch_disponible_requiere_presente · no se puede ofrecer lo",
        "que no está en el disco.",
        "CHECK ck_m05_ch_retirado_con_fecha · si no está presente, se sabe cuándo",
        "dejó de estarlo.",
        "UNIQUE (host_id, curso_id, curso_version_id) · una fila por versión, así",
        "queda el historial de QUÉ versión estuvo instalada en este host.",
        "ux_m05_ch_sin_version · parcial, tapa el hueco de los NULL: un UNIQUE los",
        "trata como distintos, y sin esto (host, curso, NULL) se podría insertar",
        "muchas veces.",
        "ux_m05_ch_una_disponible · parcial, solo una versión ofrecida por",
        "(host, curso); si no, el estudiante vería el curso duplicado.",
    ],
    "m05_progreso_leccion": [
        "PROGRESO · avance del estudiante en una lección.",
        "",
        "Se indexa por el CÓDIGO LÓGICO de la lección, no por su fila física.",
        "Esa es la decisión que hace que el progreso sobreviva a:",
        "  · desinstalar y reinstalar el mismo paquete",
        "  · subir de versión: la V2 tiene filas m05_leccion nuevas, pero la misma",
        "    lección conceptual conserva su codigo, así que el progreso la sigue",
        "Si apuntara a m05_leccion.id, un cambio de versión lo dejaría huérfano.",
        "",
        "Cuelga del CURSO, no de la versión: el progreso es del estudiante en el",
        "curso y no se pierde cuando el contenido se reemplaza.",
        "",
        "La nota del quiz NO se duplica aquí: su registro autoritativo es",
        "m10_quiz_intento.puntaje. El porcentaje de una lección con actividad",
        "calificable se deriva de ahí al consultarlo.",
        "",
        "CHECK ck_m05_prog_porcentaje  · entre 0 y 100, impuesto en el motor.",
        "CHECK ck_m05_prog_completada  · completada implica 100 y con fecha.",
        "UNIQUE (curso, persona, leccion_codigo) · una fila por lección y persona.",
    ],
    "m05_seccion": [
        "SECCIÓN · cuelga de la VERSIÓN, no del curso. Es el cambio central.",
        "codigo es la identidad LÓGICA, estable entre versiones",
        "('section.fracciones'); id es el registro FÍSICO ('SEC-MAT9-V1-01').",
        "Con el codigo se reconoce que la misma sección cambió de título.",
    ],
    "m05_leccion": [
        "LECCIÓN · la unidad que recorre el estudiante.",
        "codigo = identidad lógica; id = registro físico.",
        "competency_framework guarda el código del marco (un DBA, una PDA, una",
        "competencia LOMLOE). Es texto corto, no una FK.",
    ],
    "m05_leccion_item": [
        "ÍTEM DE LECCIÓN · punto de interoperabilidad.",
        "NO lleva codigo: su identidad es (lección, orden).",
        "Según el tipo apunta a un recurso, a una actividad, o a nada y usa",
        "elemento_ref como referencia externa sin FK.",
    ],
    "m05_recurso_aprendizaje": [
        "MATERIAL · cada fila es UNA versión concreta de un material.",
        "(content_ref, content_version) es UNIQUE: las v3.0, v3.1 y v3.2 de la",
        "misma lectura coexisten como filas distintas. Borrar la v3.0 rompería la",
        "V1 del curso, y por eso una fila solo se marca 'retirado'.",
        "El binario pesado vive FUERA: aquí solo hay referencia, versión y hash.",
    ],
    "m10_actividad": [
        "ACTIVIDAD · mismo patrón que los materiales.",
        "(activity_ref, version) es UNIQUE. Un intento de quiz apunta a la fila",
        "FÍSICA, así que un intento hecho con el quiz v1 sigue siendo",
        "interpretable aunque hoy se aplique el v2.",
    ],
    "m19_auditoria": [
        "AUDITORÍA · la traza de la vida del catálogo.",
        "instalada -> activada -> rollback, con actor, fecha y resultado.",
        "Un fallo de instalación queda aquí con resultado='error', escrito FUERA",
        "de la transacción que se revirtió.",
    ],
    "m10_quiz_pregunta": [
        "QUIZ · pregunta. Añadida al modelo entregado para poder registrar el",
        "quiz y sus intentos; no forma parte del catálogo versionado.",
    ],
    "m10_quiz_opcion": [
        "QUIZ · opción de respuesta. es_correcta NO se expone en el endpoint",
        "público: la clave de respuestas nunca viaja a la tableta.",
    ],
    "m10_quiz_intento": [
        "QUIZ · intento de un estudiante. pregunta_actual es lo que el profesor",
        "ve avanzar en vivo por WebSocket.",
    ],
    "m10_quiz_respuesta": [
        "QUIZ · respuesta puntual. UNIQUE (intento, pregunta): reenviar la misma",
        "pregunta actualiza la fila en vez de duplicarla, que es lo que hace",
        "inofensiva una reconexión.",
    ],
}

NOTA_FK_COMPUESTA = [
    "NOTA · en el diseño de referencia esta tabla lleva además una FK COMPUESTA",
    "(version_activa_id, id) -> m05_curso_version (id, curso_id), que garantiza",
    "en el motor que la versión activa pertenece a ESTE curso. El ORM de Django",
    "no puede expresarla —ForeignKey apunta a una sola columna—, así que la",
    "invariante se impone en exams.catalog.activate_version(), único camino por",
    "el que se mueve el puntero, y está cubierta por pruebas.",
]


def partir_columnas(cuerpo):
    """
    Parte el interior de un CREATE TABLE en sus definiciones de nivel superior.

    No se puede usar split(',') porque hay comas dentro de varchar(9,2), dentro
    de los CHECK y dentro de las listas de UNIQUE(...). Se lleva la cuenta de
    paréntesis y de comillas.
    """
    partes = []
    actual = []
    profundidad = 0
    comilla = None
    for ch in cuerpo:
        if comilla:
            actual.append(ch)
            if ch == comilla:
                comilla = None
            continue
        if ch in ("'", '"'):
            comilla = ch
            actual.append(ch)
            continue
        if ch == "(":
            profundidad += 1
        elif ch == ")":
            profundidad -= 1
        if ch == "," and profundidad == 0:
            partes.append("".join(actual).strip())
            actual = []
            continue
        actual.append(ch)
    if "".join(actual).strip():
        partes.append("".join(actual).strip())
    return partes


def reformatear(sql, tabla):
    """Una columna por línea, con el bloque de comentarios de la tabla dentro."""
    inicio = sql.find("(")
    fin = sql.rfind(")")
    if inicio == -1 or fin == -1:
        return sql

    cabecera = sql[:inicio].strip()
    cuerpo = sql[inicio + 1:fin]
    columnas = partir_columnas(cuerpo)

    lineas = [f"{cabecera} ("]
    for texto in DESCRIPCIONES.get(tabla, []):
        lineas.append(f"  -- {texto}")
    if tabla == "m05_curso":
        lineas.append("  --")
        for texto in NOTA_FK_COMPUESTA:
            lineas.append(f"  -- {texto}")
    if DESCRIPCIONES.get(tabla):
        lineas.append("  --" + "-" * 68)

    for i, columna in enumerate(columnas):
        coma = "," if i < len(columnas) - 1 else ""
        lineas.append(f"  {columna}{coma}")
    lineas.append(")")
    return "\n".join(lineas)


class Command(BaseCommand):
    help = "Exporta un SQLite con solo las tablas del dominio, listo para DBeaver."

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            default=None,
            help="Ruta del .db a generar. Por omisión: docs/modelo_datos_actual.db",
        )
        parser.add_argument(
            "--sin-datos",
            action="store_true",
            help="Exporta solo la estructura, sin filas.",
        )

    def handle(self, *args, **options):
        origen = settings.DATABASES["default"]["NAME"]
        if not os.path.exists(origen):
            raise CommandError(f"No encuentro la base de origen: {origen}")

        salida = options["salida"]
        if not salida:
            raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            raiz = os.path.dirname(os.path.dirname(os.path.dirname(raiz)))
            salida = os.path.join(raiz, "docs", "modelo_datos_actual.db")
        salida = os.path.abspath(salida)
        os.makedirs(os.path.dirname(salida), exist_ok=True)
        if os.path.exists(salida):
            try:
                os.remove(salida)
            except PermissionError:
                # Caso típico: DBeaver tiene el archivo abierto. Un traceback de
                # PermissionError no le dice a nadie qué hacer.
                raise CommandError(
                    f"No puedo reemplazar {salida}: otro programa lo tiene abierto.\n"
                    "Suele ser DBeaver. Dos salidas:\n"
                    "  · cierra la conexión en DBeaver (clic derecho > Desconectar) y repite, o\n"
                    "  · exporta a otro archivo:  manage.py export_schema_db --salida <ruta.db>"
                ) from None

        src = sqlite3.connect(origen)
        src.row_factory = sqlite3.Row
        dst = sqlite3.connect(salida)

        tablas = [
            r["name"]
            for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if r["name"].startswith(PREFIJOS_DOMINIO)
        ]
        if not tablas:
            raise CommandError("No encontré tablas del dominio en la base de origen.")

        # Las FK se apagan mientras se crea y se llena: el orden de inserción
        # entre tablas que se referencian mutuamente no importa así, y al final
        # se comprueba que todo cierre.
        dst.execute("PRAGMA foreign_keys = OFF")

        self.stdout.write(self.style.MIGRATE_HEADING("Estructura"))
        for tabla in tablas:
            sql = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
            ).fetchone()["sql"]
            dst.execute(reformatear(sql, tabla))
            marca = "documentada" if tabla in DESCRIPCIONES else "sin descripción"
            self.stdout.write(f"  {tabla:<28} {marca}")

        self.stdout.write(self.style.MIGRATE_HEADING("Índices"))
        n_idx = 0
        for fila in src.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL ORDER BY tbl_name, name"
        ):
            if not fila["tbl_name"].startswith(PREFIJOS_DOMINIO):
                continue
            dst.execute(fila["sql"])
            n_idx += 1
            parcial = " (parcial)" if " WHERE " in (fila["sql"] or "").upper() else ""
            self.stdout.write(f"  {fila['name']}{parcial}")
        self.stdout.write(f"  -> {n_idx} índices")

        copiadas = {}
        if not options["sin_datos"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Datos"))
            for tabla in tablas:
                filas = src.execute(f"SELECT * FROM [{tabla}]").fetchall()
                if filas:
                    columnas = filas[0].keys()
                    marcas = ",".join("?" * len(columnas))
                    lista = ",".join(f"[{c}]" for c in columnas)
                    dst.executemany(
                        f"INSERT INTO [{tabla}] ({lista}) VALUES ({marcas})",
                        [tuple(f) for f in filas],
                    )
                copiadas[tabla] = len(filas)
                self.stdout.write(f"  {tabla:<28} {len(filas)} filas")

        dst.commit()

        # Verificación: la base exportada tiene que quedar tan sana como la viva.
        dst.execute("PRAGMA foreign_keys = ON")
        integridad = dst.execute("PRAGMA integrity_check").fetchone()[0]
        huerfanos = dst.execute("PRAGMA foreign_key_check").fetchall()

        self.stdout.write(self.style.MIGRATE_HEADING("Verificación"))
        self.stdout.write(f"  integrity_check    {integridad}")
        self.stdout.write(f"  foreign_key_check  {'limpio' if not huerfanos else huerfanos}")

        problemas = []
        if integridad != "ok":
            problemas.append(f"integrity_check devolvió {integridad!r}")
        if huerfanos:
            problemas.append(f"{len(huerfanos)} referencia(s) rota(s)")
        for tabla, esperado in copiadas.items():
            real = dst.execute(f"SELECT count(*) FROM [{tabla}]").fetchone()[0]
            if real != esperado:
                problemas.append(f"{tabla}: se copiaron {real} de {esperado}")

        dst.close()
        src.close()

        if problemas:
            os.remove(salida)
            raise CommandError(
                "La exportación no quedó sana y se descartó:\n  - " + "\n  - ".join(problemas)
            )

        tamano = os.path.getsize(salida)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(tablas)} tablas y {n_idx} índices exportados a:\n  {salida}\n"
                f"  ({tamano:,} bytes) · ábrelo en DBeaver como SQLite"
            )
        )
