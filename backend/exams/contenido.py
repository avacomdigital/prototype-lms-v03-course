"""
El único sitio del LMS que habla con AVACOM-Contenido.

AVACOM-Contenido es otro producto: la biblioteca cifrada que corre en el mismo
equipo maestro del aula. Escucha solo en 127.0.0.1, en un puerto que cambia en
cada arranque, y exige una ficha. Deja las dos cosas escritas en una nota:

    %ProgramData%\\AVACOM\\contenido\\enlace.json
    {"Contrato": 1, "Puerto": 51234, "Ficha": "…64 hex…", "Proceso": 8123}

Cuatro reglas gobiernan este módulo, y las cuatro son de su constitución:

  · Artículo 4 · el LMS NO lee su base de datos. Solo su API.
  · Artículo 6 · se guarda `ref` + `version`, nunca el título. Por eso aquí no
    hay caché de catálogo: lo que se muestra se pide.
  · Artículo 8 · el LMS no guarda un catálogo propio. Cachear «para que vaya
    rápido» acaba ofreciendo material que la escuela desactivó.
  · Artículo 9 · sin contenido, el LMS sigue funcionando. Cuando el componente
    no está, esto devuelve un estado degradado, no una excepción que reviente
    una pantalla.

Si aparece otro HttpClient en el LMS apuntando a 127.0.0.1, está mal: la
política de reintentos, la revalidación de la ficha y el manejo de «no hay
contenido» se escriben una sola vez, y se escriben aquí.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

# La versión del contrato que este LMS sabe leer. El componente sube este número
# solo cuando cambia la FORMA de una respuesta de manera que rompa a quien ya la
# lee; añadir campos o rutas no lo sube. Por eso comparamos por igualdad de mayor
# y no exigimos una versión exacta de todo lo demás.
CONTRATO_SOPORTADO = 1

# Es loopback: si no contesta en un segundo, no va a contestar. Un timeout largo
# aquí congela la pantalla del profesor delante de la clase.
TIEMPO_ESPERA_SEG = 3.0

# Las capacidades que este LMS sabe aprovechar si el componente las declara.
# Un componente que no declare `capacidades` equivale a la lista vacía: se
# muestra el catálogo y se esconden los exámenes. Degrada, no se rompe.
CAPACIDAD_LECCION = "leccion"
CAPACIDAD_EVALUACION = "evaluacion"
CAPACIDAD_BANCO = "banco"
CAPACIDAD_COMPROBAR = "comprobar"
CAPACIDAD_MEDIO = "medio"
CAPACIDAD_REPASO = "repaso"


class ContenidoNoDisponible(Exception):
    """
    No hay componente con el que hablar.

    Es una situación NORMAL, no un error del LMS: el aula puede no tener la
    biblioteca instalada, o estar cerrada. Quien llame decide si degrada la
    pantalla o avisa; lo que no debe hacer es propagarlo como un 500.
    """


class ContenidoError(Exception):
    """El componente contestó, pero con un error. Lleva el código y el motivo."""

    def __init__(self, estado, detalle=""):
        super().__init__(detalle or f"El componente respondió {estado}.")
        self.estado = estado
        self.detalle = detalle


def ruta_enlace():
    """
    Dónde está la nota del componente.

    Se puede forzar con AVACOM_CONTENIDO_ENLACE, y eso es lo que permite probar
    la integración sin instalar la biblioteca.
    """
    forzada = getattr(settings, "AVACOM_CONTENIDO_ENLACE", None) or os.environ.get(
        "AVACOM_CONTENIDO_ENLACE"
    )
    if forzada:
        return forzada
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return os.path.join(base, "AVACOM", "contenido", "enlace.json")


def leer_enlace():
    """
    Lee la nota. Devuelve (puerto, ficha, contrato).

    La nota se reescribe en cada arranque del componente, así que NO se cachea:
    guardarla en memoria es la forma segura de seguir hablando con un puerto que
    ya no existe.
    """
    ruta = ruta_enlace()
    try:
        with open(ruta, encoding="utf-8") as archivo:
            nota = json.load(archivo)
    except FileNotFoundError as exc:
        raise ContenidoNoDisponible(
            "No hay ninguna biblioteca AVACOM-Contenido publicada en este equipo."
        ) from exc
    except (OSError, ValueError) as exc:
        raise ContenidoNoDisponible(
            f"La nota de enlace del componente no se pudo leer: {exc}"
        ) from exc

    # El componente escribe las claves en PascalCase; se aceptan las dos formas
    # para no atarse a un detalle de serialización del otro lado.
    def campo(*nombres):
        for nombre in nombres:
            if nombre in nota:
                return nota[nombre]
        return None

    puerto = campo("Puerto", "puerto")
    ficha = campo("Ficha", "ficha")
    contrato = campo("Contrato", "contrato")
    proceso = campo("Proceso", "proceso")

    if not puerto or not ficha:
        raise ContenidoNoDisponible("La nota de enlace está incompleta.")
    if contrato is not None and int(contrato) > CONTRATO_SOPORTADO:
        raise ContenidoNoDisponible(
            f"El componente habla el contrato {contrato} y este LMS entiende hasta "
            f"el {CONTRATO_SOPORTADO}. Hay que actualizar el LMS antes de usarlo."
        )
    return int(puerto), str(ficha), int(contrato or CONTRATO_SOPORTADO), int(proceso or 0)


def proceso_vivo(pid):
    """
    Si el proceso que dejó la nota sigue existiendo. Solo CONSULTA.

    Hace falta porque la nota es un archivo y sobrevive al proceso que la
    escribió; y porque puede haber dos componentes en la misma máquina —la
    aplicación real y un host de pruebas— peleándose ese archivo, con lo que el
    LMS acaba hablando con el que arrancó último sin que nadie lo note.

    NO se usa os.kill(pid, 0). En Windows eso no es una consulta: CPython lo
    traduce a TerminateProcess, así que preguntar «¿estás vivo?» mataría la
    biblioteca en mitad de una clase. Se abre un handle de solo consulta y se
    cierra.

    Devuelve None cuando no se puede saber, que no es lo mismo que «no está».
    """
    if not pid:
        return None

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            error = ctypes.get_last_error()
            # 87 ERROR_INVALID_PARAMETER es lo que devuelve un pid que ya no
            # existe. 5 ACCESO_DENEGADO significa que existe pero es de otro
            # usuario o de mayor integridad: existe.
            if error == 87:
                return False
            return True if error == 5 else None
        try:
            codigo = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo)):
                return codigo.value == STILL_ACTIVE
            return None
        finally:
            kernel32.CloseHandle(handle)

    # En POSIX la señal 0 sí es una consulta y no entrega nada al proceso.
    import errno

    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return None if getattr(exc, "errno", None) != errno.ESRCH else False


def _pedir(metodo, camino, consulta=None, cuerpo=None):
    puerto, ficha, _, _ = leer_enlace()
    url = f"http://127.0.0.1:{puerto}{camino}"
    if consulta:
        limpio = {k: v for k, v in consulta.items() if v not in (None, "")}
        if limpio:
            url = f"{url}?{urllib.parse.urlencode(limpio)}"

    datos = None
    cabeceras = {"X-Avacom-Ficha": ficha, "Accept": "application/json"}
    if cuerpo is not None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"

    peticion = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA_SEG) as respuesta:
            crudo = respuesta.read().decode("utf-8") or "null"
            return json.loads(crudo)
    except urllib.error.HTTPError as exc:
        detalle = ""
        try:
            detalle = exc.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001 - el detalle es informativo
            pass
        raise ContenidoError(exc.code, detalle) from exc
    except urllib.error.URLError as exc:
        # El puerto está en la nota pero nadie escucha: el componente se cerró.
        raise ContenidoNoDisponible(
            f"La biblioteca no responde en 127.0.0.1:{puerto} ({exc.reason})."
        ) from exc
    except (TimeoutError, ValueError) as exc:
        raise ContenidoNoDisponible(f"La biblioteca no contestó a tiempo: {exc}") from exc


# ── Las cinco rutas que el componente ya tiene ───────────────────────────────
def salud():
    return _pedir("GET", "/v1/salud")


def catalogo(**filtros):
    """
    El catálogo, con la política del administrador YA aplicada por el componente.

    Lo desactivado por la escuela no llega atenuado ni con una marca: no llega.
    Si llegara, el LMS acabaría mostrándolo.
    """
    return _pedir("GET", "/v1/catalogo", consulta=filtros)


def taxonomia(padre=None):
    return _pedir("GET", "/v1/taxonomia", consulta={"padre": padre})


def elemento(referencia):
    return _pedir("GET", f"/v1/elemento/{urllib.parse.quote(referencia, safe='')}")


def mostrar(referencia, persona_id=None):
    cuerpo = {"elemento_ref": referencia}
    if persona_id:
        cuerpo["persona_id"] = persona_id
    return _pedir("POST", "/v1/mostrar", cuerpo=cuerpo)


# ── Las seis del D-2, todavía por construir del otro lado ────────────────────
# Se escriben ya para que el LMS no tenga que cambiar cuando aparezcan, y cada
# una se protege con su capacidad: llamarlas contra un componente que no las
# tiene da un mensaje claro en vez de un 404 sin explicación.
def _exigir(capacidad, capacidades):
    if capacidad not in (capacidades or []):
        raise ContenidoError(
            501,
            f"La biblioteca instalada no ofrece «{capacidad}». Es una capacidad "
            f"prevista del contrato que esta versión del componente todavía no "
            f"publica.",
        )


def leccion(referencia, capacidades=None):
    _exigir(CAPACIDAD_LECCION, capacidades)
    return _pedir("GET", f"/v1/leccion/{urllib.parse.quote(referencia, safe='')}")


def evaluacion(referencia, capacidades=None):
    _exigir(CAPACIDAD_EVALUACION, capacidades)
    return _pedir("GET", f"/v1/evaluacion/{urllib.parse.quote(referencia, safe='')}")


def extraer_banco(referencia, capacidades=None, **parametros):
    _exigir(CAPACIDAD_BANCO, capacidades)
    return _pedir(
        "POST", f"/v1/banco/{urllib.parse.quote(referencia, safe='')}/extraer",
        cuerpo=parametros or {},
    )


def comprobar(pregunta_ref, respuesta, capacidades=None):
    """
    Califica UNA pregunta, en el componente.

    Devuelve {acierta: bool} y la retroalimentación que la pregunta ya trae. La
    clave de respuesta no viaja: se compara donde vive. Esta función es el único
    punto del LMS que la toca, y la toca sin verla.
    """
    _exigir(CAPACIDAD_COMPROBAR, capacidades)
    return _pedir(
        "POST", "/v1/comprobar",
        cuerpo={"pregunta_ref": pregunta_ref, "respuesta": respuesta},
    )


def medio(referencia, capacidades=None):
    """Abre una sesión de bytes. La dirección es de un solo uso y por loopback."""
    _exigir(CAPACIDAD_MEDIO, capacidades)
    return _pedir("GET", f"/v1/medio/{urllib.parse.quote(referencia, safe='')}")


def repaso(referencia, segundos=None, persona_id=None, capacidades=None):
    """
    Apunta que alguien abrió algo por su cuenta.

    Escribe en m08_repaso_* del componente y NO genera intento ni nota: es el
    artículo 12 y es una regla, no una preferencia.
    """
    _exigir(CAPACIDAD_REPASO, capacidades)
    cuerpo = {"elemento_ref": referencia}
    if segundos is not None:
        cuerpo["segundos"] = int(segundos)
    if persona_id:
        cuerpo["persona_id"] = persona_id
    return _pedir("POST", "/v1/repaso", cuerpo=cuerpo)


# ── Estado, que es lo que consulta toda pantalla antes de ofrecer nada ───────
def estado():
    """
    Si el componente está, qué contrato habla y qué sabe hacer.

    Nunca lanza: devuelve `disponible=False` con el motivo. Es el artículo 9
    hecho función — una pantalla del LMS no puede quedarse en blanco porque la
    biblioteca esté cerrada.
    """
    try:
        datos = salud()
    except ContenidoNoDisponible as exc:
        return {
            "disponible": False,
            "motivo": str(exc),
            "puerto": None,
            "proceso": None,
            "proceso_vivo": None,
            "contrato": None,
            "generacion": None,
            "capacidades": [],
            "conteos": {},
        }
    except ContenidoError as exc:
        return {
            "disponible": False,
            "motivo": f"La biblioteca respondió {exc.estado}: {exc.detalle}"[:400],
            "puerto": None,
            "proceso": None,
            "proceso_vivo": None,
            "contrato": None,
            "generacion": None,
            "capacidades": [],
            "conteos": {},
        }

    capacidades = list(datos.get("capacidades") or [])
    try:
        puerto, _, _, pid = leer_enlace()
    except ContenidoNoDisponible:
        puerto, pid = None, None

    return {
        "disponible": True,
        # Quién atiende. Con dos componentes en la máquina, esto es lo único que
        # dice cuál de los dos está contestando.
        "puerto": puerto,
        "proceso": pid,
        "proceso_vivo": proceso_vivo(pid),
        "motivo": "",
        "componente": datos.get("componente"),
        "contrato": datos.get("contrato"),
        # `generacion` es la señal barata de «el catálogo cambió». Cuando el
        # componente todavía no la publique, se deriva de los contadores: es peor
        # —no detecta un cambio que deje los totales iguales— pero es mejor que
        # sondear el disco, y desaparece sola en cuanto llegue la de verdad.
        "generacion": datos.get("generacion"),
        "generacion_derivada": datos.get("generacion") is None,
        "huella_catalogo": _huella_catalogo(datos),
        "capacidades": capacidades,
        "conteos": {
            "elementos": datos.get("elementos"),
            "paquetes": datos.get("paquetes"),
            "politicas": datos.get("politicas"),
        },
    }


def _huella_catalogo(datos):
    """
    Con qué se detecta que el catálogo cambió, en orden de preferencia.

    1. `generacion` — el contador monótono del D-3, lo más fiable.
    2. `huella_catalogo` — el componente ya lo publica y sirve igual: cambia
       cuando cambia el catálogo, aunque no diga en qué dirección.
    3. Los contadores — el último recurso. No detecta un cambio que deje los
       totales iguales, y por eso se prefiere cualquiera de los dos anteriores.
    """
    generacion = datos.get("generacion")
    if generacion is not None:
        return f"g{generacion}"
    propia = datos.get("huella_catalogo")
    if propia:
        return f"h{propia}"
    return "c{}-{}-{}".format(
        datos.get("elementos"), datos.get("paquetes"), datos.get("politicas")
    )
