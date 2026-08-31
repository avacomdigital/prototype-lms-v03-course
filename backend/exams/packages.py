"""
Lectura de paquetes de curso: SCORM y CMI5.

El punto de todo este módulo es que SCORM y CMI5 son formatos de ENTRADA, no
modelos distintos de curso. Cada parser produce la MISMA estructura intermedia
—el mismo dict que ya consume exams.package_install— y de ahí en adelante el
resto del sistema no sabe de qué formato venía:

    .zip
      │
      ├── imsmanifest.xml ──> parser SCORM ──┐
      └── cmi5.xml ────────> parser CMI5  ──┤
                                             ▼
                              avacom-course-package/v1
                                             │
                                             ▼
                       curso -> sección -> lección -> lesson item

Fuera de alcance a propósito (§23 del spec): las reglas de sequencing de SCORM
2004, el LRS de CMI5, xAPI, y los detalles de runtime de las AU (moveOn,
masteryScore, launchMethod). Aquí solo se lee la ESTRUCTURA.
"""

import hashlib
import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree

FORMATO_SCORM_12 = "scorm_12"
FORMATO_SCORM_2004 = "scorm_2004"
FORMATO_CMI5 = "cmi5"

MANIFIESTO_SCORM = "imsmanifest.xml"
MANIFIESTO_CMI5 = "cmi5.xml"

# Extensiones que deciden si un recurso es lectura, video o audio. El modelo solo
# admite esos tres valores en content_type.
TIPOS_POR_EXTENSION = {
    ".mp4": "video", ".webm": "video", ".mov": "video", ".avi": "video",
    ".mp3": "audio", ".m4a": "audio", ".ogg": "audio", ".wav": "audio",
}


class PackageFormatError(Exception):
    """El .zip no es un paquete que sepamos leer."""


def _sin_ns(etiqueta):
    """'{http://...}organization' -> 'organization'."""
    return etiqueta.rsplit("}", 1)[-1] if "}" in etiqueta else etiqueta


def _hijos(nodo, nombre):
    return [h for h in nodo if _sin_ns(h.tag) == nombre]


def _hijo(nodo, nombre):
    encontrados = _hijos(nodo, nombre)
    return encontrados[0] if encontrados else None


def _texto(nodo, nombre, defecto=None):
    hijo = _hijo(nodo, nombre)
    if hijo is None or hijo.text is None:
        return defecto
    valor = hijo.text.strip()
    return valor or defecto


def _slug(texto, prefijo):
    base = (texto or "").lower()
    for original, limpio in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"),
                             ("ú", "u"), ("ñ", "n"), ("ü", "u")):
        base = base.replace(original, limpio)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return f"{prefijo}.{base or 'sin-titulo'}"[:120]


def _tipo_contenido(ruta):
    for extension, tipo in TIPOS_POR_EXTENSION.items():
        if (ruta or "").lower().endswith(extension):
            return tipo
    return "reading"


def detect_format(datos_zip):
    """
    Qué formato es, mirando qué descriptor trae el paquete.

    Devuelve (formato, manifest_tipo, manifest_ref). Si trae los dos
    descriptores gana CMI5, porque es el más específico: un paquete que declara
    cmi5.xml quiere ejecutarse como CMI5.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(datos_zip)) as zf:
            nombres = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise PackageFormatError("El archivo no es un .zip válido.") from exc

    def buscar(objetivo):
        for nombre in nombres:
            if posixpath.basename(nombre).lower() == objetivo:
                return nombre
        return None

    ruta_cmi5 = buscar(MANIFIESTO_CMI5)
    if ruta_cmi5:
        return FORMATO_CMI5, "cmi5", ruta_cmi5

    ruta_scorm = buscar(MANIFIESTO_SCORM)
    if ruta_scorm:
        with zipfile.ZipFile(io.BytesIO(datos_zip)) as zf:
            xml = zf.read(ruta_scorm).decode("utf-8", "replace")
        # El schemaversion del manifest distingue 1.2 de 2004.
        formato = FORMATO_SCORM_2004 if "2004" in xml or "CAM 1.3" in xml else FORMATO_SCORM_12
        return formato, "imsmanifest", ruta_scorm

    raise PackageFormatError(
        f"El .zip no trae ni {MANIFIESTO_CMI5} ni {MANIFIESTO_SCORM}. "
        "No se reconoce como paquete SCORM ni CMI5."
    )


def _huella(datos):
    return hashlib.sha256(datos).hexdigest()


# ── SCORM ────────────────────────────────────────────────────────────────────
def _parse_scorm(datos_zip, ruta_manifest, formato):
    """
    imsmanifest.xml -> estructura intermedia.

    El mapeo que usa el spec (§2.1 de la propuesta previa):
        organization      -> curso
        item nivel 1      -> sección
        item nivel 2      -> lección
        item hoja         -> lesson item
        resource          -> recurso o actividad

    Un `item` con identifierref apunta a un `resource`; sin él es un contenedor.
    """
    with zipfile.ZipFile(io.BytesIO(datos_zip)) as zf:
        raiz = ElementTree.fromstring(zf.read(ruta_manifest))

    package_identifier = raiz.get("identifier") or "paquete-scorm"
    package_version = raiz.get("version")

    # resources: identifier -> href
    recursos_xml = {}
    contenedor = _hijo(raiz, "resources")
    if contenedor is not None:
        for recurso in _hijos(contenedor, "resource"):
            ident = recurso.get("identifier")
            if not ident:
                continue
            href = recurso.get("href")
            if not href:
                archivo = _hijo(recurso, "file")
                href = archivo.get("href") if archivo is not None else None
            recursos_xml[ident] = {
                "href": href,
                "scormtype": (
                    recurso.get("{http://www.adlnet.org/xsd/adlcp_rootv1p2}scormtype")
                    or recurso.get("{http://www.adlnet.org/xsd/adlcp_v1p3}scormType")
                    or recurso.get("scormtype")
                ),
            }

    organizaciones = _hijo(raiz, "organizations")
    if organizaciones is None:
        raise PackageFormatError("El imsmanifest.xml no trae <organizations>.")
    por_omision = organizaciones.get("default")
    lista = _hijos(organizaciones, "organization")
    if not lista:
        raise PackageFormatError("El imsmanifest.xml no trae ninguna <organization>.")
    organizacion = next((o for o in lista if o.get("identifier") == por_omision), lista[0])

    titulo_curso = _texto(organizacion, "title", package_identifier)
    org_id = organizacion.get("identifier")

    recursos = {}
    actividades = {}
    secciones = []

    for indice_sec, item_sec in enumerate(_hijos(organizacion, "item"), start=1):
        titulo_sec = _texto(item_sec, "title", f"Sección {indice_sec}")
        lecciones = []
        hijos_leccion = _hijos(item_sec, "item")

        # Una sección SCORM puede ser hoja: entonces ella misma es la lección.
        if not hijos_leccion:
            hijos_leccion = [item_sec]

        for indice_lec, item_lec in enumerate(hijos_leccion, start=1):
            titulo_lec = _texto(item_lec, "title", f"Lección {indice_lec}")
            hojas = _hijos(item_lec, "item") or [item_lec]
            items = []
            for indice_item, hoja in enumerate(hojas, start=1):
                ref = hoja.get("identifierref")
                if not ref or ref not in recursos_xml:
                    continue
                entrada = _item_desde_recurso(
                    hoja, recursos_xml[ref], ref, indice_item, recursos, actividades,
                    prefijo_ref=f"scorm:{org_id}",
                )
                if entrada:
                    items.append(entrada)

            if not items:
                # Una lección sin ítems no es navegable; el instalador la rechaza.
                # Se le cuelga una referencia externa al propio item del manifest.
                items = [{
                    "orden": 1,
                    "tipo": "referencia_externa",
                    "elemento_ref": f"scorm:{org_id}/{item_lec.get('identifier') or titulo_lec}",
                    "elemento_version": "1.0",
                }]

            lecciones.append({
                "codigo": _slug(item_lec.get("identifier") or titulo_lec, "lesson"),
                "titulo": titulo_lec,
                "descripcion": None,
                "competency_framework": None,
                "learning_outcome": None,
                "skills": None,
                "attitudes_values": None,
                "orden": indice_lec,
                "estado": "publicado",
                "items": items,
            })

        secciones.append({
            "codigo": _slug(item_sec.get("identifier") or titulo_sec, "section"),
            "titulo": titulo_sec,
            "orden": indice_sec,
            "lessons": lecciones,
        })

    return {
        "titulo_curso": titulo_curso,
        "formato_contenido": formato,
        "manifest_tipo": "imsmanifest",
        "manifest_ref": ruta_manifest,
        "package_identifier": package_identifier,
        "package_version": package_version,
        "scorm_organization_id": org_id,
        "recursos": list(recursos.values()),
        "actividades": list(actividades.values()),
        "secciones": secciones,
    }


def _item_desde_recurso(hoja, recurso_xml, ref, orden, recursos, actividades, prefijo_ref):
    """
    Un `resource` de SCORM puede ser un asset (contenido) o un SCO (actividad).

    scormtype='sco' significa que se comunica con el runtime: eso es una
    actividad. 'asset' es material estático.
    """
    href = recurso_xml.get("href") or ref
    titulo = _texto(hoja, "title", href)
    es_sco = (recurso_xml.get("scormtype") or "").lower() == "sco"
    logico = f"{prefijo_ref}/{ref}"

    if es_sco:
        actividades[logico] = {
            "id": None,
            "activity_ref": logico,
            "version": 1,
            "titulo": titulo,
            "descripcion": f"SCO del paquete SCORM · {href}",
            "activity_type": "assignment",
            "submission_type": "none",
            "grading_type": "teacher",
            "max_score": 100,
            "autor_id": "importador-scorm",
        }
        return {
            "orden": orden,
            "tipo": "actividad",
            "activity_ref": logico,
            "activity_version": 1,
        }

    recursos[logico] = {
        "id": None,
        "titulo": titulo,
        "content_type": _tipo_contenido(href),
        "content_ref": logico,
        "content_version": "1.0",
        "content_huella": None,
        "duracion_seg": None,
        "autor_id": "importador-scorm",
    }
    return {
        "orden": orden,
        "tipo": "contenido",
        "content_ref": logico,
        "content_version": "1.0",
    }


# ── CMI5 ─────────────────────────────────────────────────────────────────────
def _parse_cmi5(datos_zip, ruta_manifest):
    """
    cmi5.xml -> estructura intermedia.

    CMI5 organiza el curso en Course / Block / AU:
        course          -> curso
        block nivel 1   -> sección
        block nivel 2   -> lección
        au              -> lesson item de tipo actividad

    Las AU son unidades lanzables que reportan por xAPI, así que se importan como
    ACTIVIDADES, no como contenido. moveOn, masteryScore y launchMethod se leen
    solo para describir la actividad; el runtime queda fuera de alcance.
    """
    with zipfile.ZipFile(io.BytesIO(datos_zip)) as zf:
        raiz = ElementTree.fromstring(zf.read(ruta_manifest))

    curso_xml = _hijo(raiz, "course")
    if curso_xml is None:
        raise PackageFormatError("El cmi5.xml no trae <course>.")

    package_identifier = curso_xml.get("id") or "paquete-cmi5"
    titulo_curso = _titulo_cmi5(curso_xml) or package_identifier

    recursos = {}
    actividades = {}
    secciones = []
    contadores = {"seccion": 0}

    bloques = _hijos(raiz, "block")
    aus_sueltas = _hijos(raiz, "au")

    if bloques:
        for bloque in bloques:
            contadores["seccion"] += 1
            secciones.append(_seccion_cmi5(bloque, contadores["seccion"], actividades, recursos))
    if aus_sueltas:
        # AU en la raíz, sin bloque: se agrupan en una sección propia para que el
        # árbol de AVACOM quede completo.
        contadores["seccion"] += 1
        lecciones = [
            _leccion_desde_au(au, indice, actividades)
            for indice, au in enumerate(aus_sueltas, start=1)
        ]
        secciones.append({
            "codigo": "section.unidades",
            "titulo": "Unidades",
            "orden": contadores["seccion"],
            "lessons": lecciones,
        })

    if not secciones:
        raise PackageFormatError("El cmi5.xml no trae ni <block> ni <au>.")

    return {
        "titulo_curso": titulo_curso,
        "formato_contenido": FORMATO_CMI5,
        "manifest_tipo": "cmi5",
        "manifest_ref": ruta_manifest,
        "package_identifier": package_identifier,
        "package_version": None,
        "scorm_organization_id": None,
        "recursos": list(recursos.values()),
        "actividades": list(actividades.values()),
        "secciones": secciones,
    }


def _titulo_cmi5(nodo):
    """El título en CMI5 es <title><langstring>Texto</langstring></title>."""
    titulo = _hijo(nodo, "title")
    if titulo is None:
        return None
    cadena = _hijo(titulo, "langstring")
    if cadena is not None and cadena.text:
        return cadena.text.strip()
    return (titulo.text or "").strip() or None


def _seccion_cmi5(bloque, orden, actividades, recursos):
    titulo = _titulo_cmi5(bloque) or f"Bloque {orden}"
    identificador = bloque.get("id") or titulo

    lecciones = []
    sub_bloques = _hijos(bloque, "block")
    aus = _hijos(bloque, "au")

    indice = 0
    for sub in sub_bloques:
        indice += 1
        # Un bloque anidado es una lección; sus AU son sus ítems.
        titulo_lec = _titulo_cmi5(sub) or f"Lección {indice}"
        items = []
        for pos, au in enumerate(_hijos(sub, "au"), start=1):
            items.append(_item_desde_au(au, pos, actividades))
        if not items:
            items = [{
                "orden": 1, "tipo": "referencia_externa",
                "elemento_ref": f"cmi5:{sub.get('id') or titulo_lec}",
                "elemento_version": "1.0",
            }]
        lecciones.append({
            "codigo": _slug(sub.get("id") or titulo_lec, "lesson"),
            "titulo": titulo_lec,
            "descripcion": None,
            "competency_framework": None,
            "learning_outcome": None,
            "skills": None,
            "attitudes_values": None,
            "orden": indice,
            "estado": "publicado",
            "items": items,
        })

    for au in aus:
        indice += 1
        lecciones.append(_leccion_desde_au(au, indice, actividades))

    if not lecciones:
        lecciones = [{
            "codigo": _slug(identificador, "lesson"),
            "titulo": titulo,
            "descripcion": None,
            "competency_framework": None,
            "learning_outcome": None,
            "skills": None,
            "attitudes_values": None,
            "orden": 1,
            "estado": "publicado",
            "items": [{
                "orden": 1, "tipo": "referencia_externa",
                "elemento_ref": f"cmi5:{identificador}", "elemento_version": "1.0",
            }],
        }]

    return {
        "codigo": _slug(identificador, "section"),
        "titulo": titulo,
        "orden": orden,
        "lessons": lecciones,
    }


def _leccion_desde_au(au, orden, actividades):
    """Una AU suelta se convierte en una lección con un único ítem: la propia AU."""
    titulo = _titulo_cmi5(au) or au.get("id") or f"Unidad {orden}"
    return {
        "codigo": _slug(au.get("id") or titulo, "lesson"),
        "titulo": titulo,
        "descripcion": _descripcion_cmi5(au),
        "competency_framework": None,
        "learning_outcome": None,
        "skills": None,
        "attitudes_values": None,
        "orden": orden,
        "estado": "publicado",
        "items": [_item_desde_au(au, 1, actividades)],
    }


def _descripcion_cmi5(nodo):
    descripcion = _hijo(nodo, "description")
    if descripcion is None:
        return None
    cadena = _hijo(descripcion, "langstring")
    if cadena is not None and cadena.text:
        return cadena.text.strip()
    return (descripcion.text or "").strip() or None


def _item_desde_au(au, orden, actividades):
    """
    Una AU es una unidad LANZABLE que reporta por xAPI: se importa como actividad.

    masteryScore y moveOn se leen solo para describirla. El runtime —lanzar la AU
    y recibir sus statements— queda fuera del alcance de este prototipo.
    """
    identificador = au.get("id") or f"au-{orden}"
    titulo = _titulo_cmi5(au) or identificador
    logico = identificador if identificador.startswith(("http://", "https://")) else f"cmi5:{identificador}"

    mastery = au.get("masteryScore")
    move_on = au.get("moveOn")
    partes = [f"AU de un paquete CMI5 · launch: {au.get('url') or 'sin url'}"]
    if move_on:
        partes.append(f"moveOn={move_on}")
    if mastery:
        partes.append(f"masteryScore={mastery}")

    actividades[logico] = {
        "id": None,
        "activity_ref": logico,
        "version": 1,
        "titulo": titulo[:250],
        "descripcion": " · ".join(partes),
        "activity_type": "assignment",
        "submission_type": "none",
        "grading_type": "teacher",
        "max_score": 100,
        "autor_id": "importador-cmi5",
    }
    return {"orden": orden, "tipo": "actividad", "activity_ref": logico, "activity_version": 1}


# ── Entrada pública ──────────────────────────────────────────────────────────
def read_package(datos_zip):
    """
    Lee un .zip y devuelve la estructura intermedia, sin tocar la base.

    Es lo que alimenta la vista previa del §16 del spec: nombre detectado,
    formato detectado, identificador, versión y conteos.
    """
    formato, manifest_tipo, manifest_ref = detect_format(datos_zip)
    if formato == FORMATO_CMI5:
        leido = _parse_cmi5(datos_zip, manifest_ref)
    else:
        leido = _parse_scorm(datos_zip, manifest_ref, formato)

    leido["package_huella"] = _huella(datos_zip)
    lecciones = [l for s in leido["secciones"] for l in s["lessons"]]
    items = [i for l in lecciones for i in l["items"]]
    leido["conteos"] = {
        "secciones": len(leido["secciones"]),
        "lecciones": len(lecciones),
        "items": len(items),
        "recursos": len(leido["recursos"]),
        "actividades": len(leido["actividades"]),
    }
    return leido


def to_course_package(leido, course_id, version, activate_after_install=True, instalada_por="docente-ops"):
    """
    Convierte la estructura intermedia al paquete «avacom-course-package/v1».

    A partir de aquí el instalador transaccional que ya existe hace todo el
    trabajo, y no sabe si el origen era SCORM o CMI5. Ese es el objetivo del
    módulo: un solo camino de instalación.
    """
    def con_id(entradas, prefijo):
        salida = []
        for indice, entrada in enumerate(entradas, start=1):
            copia = dict(entrada)
            if not copia.get("id"):
                # Id determinista: el mismo paquete en dos nodos offline produce
                # los mismos ids y la sincronización no genera duplicados.
                copia["id"] = f"{prefijo}-{_slug(course_id, 'x').split('.', 1)[-1][:12]}-{indice:03d}".upper()[:40]
            salida.append(copia)
        return salida

    return {
        "schema": "avacom-course-package/v1",
        "package": {
            "package_id": leido["package_identifier"],
            "package_version": leido.get("package_version") or f"{version}.0.0",
            "operation": "install",
        },
        "course": {"course_id": course_id, "version": version},
        "publication": {"activate_after_install": activate_after_install},
        "version_meta": {
            "instalada_por": instalada_por,
            "huella": leido["package_huella"],
            "notas": (
                f"Importado de un paquete {leido['formato_contenido']} "
                f"({leido['manifest_tipo']}: {leido['manifest_ref']})."
            ),
        },
        "resources": con_id(leido["recursos"], "RES"),
        "activities": con_id(leido["actividades"], "ACT"),
        "sections": leido["secciones"],
    }
