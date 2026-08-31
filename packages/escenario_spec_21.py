"""
Escenario principal de demostración del spec (§21), ejecutado contra la API.

    Paso 1  OPS sin el curso
    Paso 2  instalar matematicas6.zip -> presente=1, disponible=1
    Paso 3  asignar Juan al curso
    Paso 4  Juan avanza: L1 100%, L2 50%, quiz 80/100
    Paso 5  desinstalar desde OPS Master -> presente=0, disponible=0
    Paso 6  Juan ve su progreso y «No disponible actualmente»
    Paso 7  verificar en base de datos que lo académico sigue
    Paso 8  reinstalar -> presente=1, disponible=1
    Paso 9  Juan continúa con el mismo progreso

Uso:
    python packages/escenario_spec_21.py
    python packages/escenario_spec_21.py --formato cmi5     # AC-11
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("AVACOM_API", "http://127.0.0.1:8000")
HOST = "OPS-AULA-01"
JUAN = "juan"
AQUI = os.path.dirname(os.path.abspath(__file__))

ok = fail = 0


def chk(etiqueta, condicion, detalle=""):
    global ok, fail
    if condicion:
        ok += 1
        print(f"  OK    {etiqueta}" + (f"  ->  {detalle}" if detalle else ""))
    else:
        fail += 1
        print(f"  FALLA {etiqueta}" + (f"  ->  {detalle}" if detalle else ""))


def call(ruta, cuerpo=None, metodo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(
        BASE + ruta, data=datos,
        headers={"Content-Type": "application/json"},
        method=metodo or ("POST" if datos else "GET"))
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            texto = r.read().decode("utf-8")
            return r.status, (json.loads(texto) if texto else None)
    except urllib.error.HTTPError as e:
        crudo = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(crudo)
        except Exception:
            return e.code, crudo


def titulo(n, texto):
    print()
    print("=" * 78)
    print(f"PASO {n} · {texto}")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--formato", choices=["scorm", "cmi5"], default="scorm")
    args = parser.parse_args()

    zip_path = os.path.join(
        AQUI, "matematicas6.zip" if args.formato == "scorm" else "matematicas6_cmi5.zip"
    )
    if not os.path.exists(zip_path):
        print(f"No encuentro {zip_path}. Corre primero construir_matematicas6.py")
        return 1
    paquete_b64 = base64.b64encode(open(zip_path, "rb").read()).decode()
    print(f"Paquete: {os.path.basename(zip_path)}  ({os.path.getsize(zip_path):,} bytes)")
    print(f"Host:    {HOST}")

    # ── PASO 1 ───────────────────────────────────────────────────────────────
    titulo(1, "La OPS todavía no tiene el curso")
    st, previo = call("/api/course-packages/install/?preview=1",
                      {"package_base64": paquete_b64, "package_name": os.path.basename(zip_path)})
    chk("la vista previa responde 200", st == 200, f"HTTP {st}")
    if st != 200:
        print("  ", previo)
        return 1
    d = previo["detected"]
    print(f"    formato detectado   {d['content_format']}")
    print(f"    descriptor          {d['manifest_type']}: {d['manifest_ref']}")
    print(f"    identificador       {d['package_identifier']}")
    print(f"    titulo detectado    {d['detected_title']}")
    print(f"    course_id derivado  {d['course_id']}")
    print(f"    conteos             {d['counts']}")
    course_id = d["course_id"]

    st, disponibles = call(f"/api/courses/available/?host_id={HOST}")
    chk("no aparece en cursos disponibles",
        not any(c["course_id"] == course_id for c in disponibles["courses"]))

    # ── PASO 2 ───────────────────────────────────────────────────────────────
    titulo(2, "Instalar el paquete")
    st, inst = call("/api/course-packages/install/", {
        "package_base64": paquete_b64,
        "package_name": os.path.basename(zip_path),
        "host_id": HOST,
        "titulo": "Matemáticas 6",
        "curriculum_framework": "MEN_CO",
        "actor": "profesor-demo",
    })
    chk("instala y responde 201", st == 201, f"HTTP {st}")
    if st not in (200, 201):
        print("  ", inst)
        return 1
    host = inst["host"]
    print(f"    {inst['message']}")
    print(f"    curso     {inst['install']['curso_titulo']}  ({inst['install']['course_id']})")
    print(f"    version   {inst['install']['version_id']}")
    print(f"    creados   {inst['install']['creados']}")
    chk("presente_local = 1", host["presente_local"] is True)
    chk("disponible_estudiante = 1", host["disponible_estudiante"] is True)
    chk("el formato quedó registrado", host["formato_contenido"] == d["content_format"],
        host["formato_contenido"])
    course_id = inst["install"]["course_id"]

    st, disponibles = call(f"/api/courses/available/?host_id={HOST}")
    chk("ahora aparece en cursos disponibles",
        any(c["course_id"] == course_id for c in disponibles["courses"]))

    # ── PASO 3 ───────────────────────────────────────────────────────────────
    titulo(3, "Asignar a Juan al curso")
    st, matricula = call("/api/enrollments/", {"curso": course_id, "persona_id": JUAN})
    chk("matricula creada", st in (200, 201), f"HTTP {st}")

    st, mis = call(f"/api/students/{JUAN}/courses/?host_id={HOST}")
    mio = next((c for c in mis["courses"] if c["course_id"] == course_id), None)
    chk("Juan ve el curso", mio is not None)
    if mio:
        chk("installed=True y available=True", mio["installed"] and mio["available"])
        chk("progreso inicial 0", mio["progress"] == 0.0, str(mio["progress"]))

    # ── PASO 4 ───────────────────────────────────────────────────────────────
    titulo(4, "Juan avanza en el curso")
    st, detalle = call(f"/api/courses/{course_id}/")
    lecciones = [
        (l["id"], l["titulo"]) for s in detalle["secciones"] for l in s["lecciones"]
    ]
    st, avance = call(f"/api/students/{JUAN}/courses/{course_id}/progress/")
    codigos = [(x["leccion_codigo"], x["titulo"]) for x in avance["detalle"]]
    print(f"    el curso tiene {len(codigos)} lecciones:")
    for c, t in codigos:
        print(f"      {t[:40]:<42} {c}")

    # L1 al 100 %, L2 al 50 %
    st, r = call(f"/api/students/{JUAN}/courses/{course_id}/progress/",
                 {"leccion_codigo": codigos[0][0], "porcentaje": 100,
                  "leccion_titulo": codigos[0][1]})
    chk("Leccion 1 -> 100%", st == 200 and r["lesson"]["porcentaje"] == 100.0)
    st, r = call(f"/api/students/{JUAN}/courses/{course_id}/progress/",
                 {"leccion_codigo": codigos[1][0], "porcentaje": 50,
                  "leccion_titulo": codigos[1][1]})
    chk("Leccion 2 -> 50%", st == 200 and r["lesson"]["porcentaje"] == 50.0)

    # El quiz. Si el paquete trae uno con preguntas se responde de verdad, para
    # que la nota salga del motor de calificación. Un SCO de SCORM y una AU de
    # CMI5 NO transportan las preguntas dentro del descriptor —eso vive en el
    # contenido del paquete y lo reporta el runtime—, así que en ese caso se
    # registra la nota como avance de la lección, que es el equivalente
    # observable del «Quiz -> 80/100» del spec.
    nota_quiz = _hacer_quiz(detalle, course_id)
    if nota_quiz is not None:
        chk("quiz respondido y calificado por el motor", nota_quiz > 0, f"{nota_quiz}/100")
    else:
        st, r = call(f"/api/students/{JUAN}/courses/{course_id}/progress/",
                     {"leccion_codigo": codigos[-1][0], "porcentaje": 80,
                      "leccion_titulo": codigos[-1][1], "actor": "runtime-scorm"})
        chk("Quiz -> 80/100 registrado como avance de su leccion",
            st == 200 and r["lesson"]["porcentaje"] == 80.0, f"HTTP {st}")
        nota_quiz = 80.0

    st, avance = call(f"/api/students/{JUAN}/courses/{course_id}/progress/")
    print(f"\n    progreso por leccion:")
    for x in avance["detalle"]:
        extra = f"  (nota {x['nota']['puntaje']:.0f}/{x['nota']['max_score']:.0f})" if x["nota"] else ""
        print(f"      {x['titulo'][:38]:<40} {x['porcentaje']:>6.2f}%  {x['estado']}{extra}")
    progreso_antes = avance["porcentaje"]
    print(f"\n    PROGRESO GENERAL: {progreso_antes}%")
    chk("hay progreso registrado", progreso_antes > 0, f"{progreso_antes}%")

    # ── PASO 5 ───────────────────────────────────────────────────────────────
    titulo(5, "Desinstalar el curso desde OPS Master")
    st, des = call(f"/api/courses/{course_id}/uninstall/",
                   {"host_id": HOST, "actor": "profesor-demo"})
    chk("desinstala y responde 200", st == 200, f"HTTP {st}")
    print(f"    {des['message']}")
    print(f"    conservado: {des['preserved']['after']}")
    chk("presente_local = 0", des["hosts"][0]["presente_local"] is False)
    chk("disponible_estudiante = 0", des["hosts"][0]["disponible_estudiante"] is False)
    chk("retirado_en sellado", des["hosts"][0]["retirado_en"] is not None)
    chk("nada academico se movio", des["preserved"]["intact"] is True,
        f"antes={des['preserved']['before']} despues={des['preserved']['after']}")
    chk("el curso NO se borro", des["course_state"] is not None, des["course_state"])

    st, disponibles = call(f"/api/courses/available/?host_id={HOST}")
    chk("AC-07 · ya no aparece en disponibles",
        not any(c["course_id"] == course_id for c in disponibles["courses"]))

    st, historial = call(f"/api/courses/history/?host_id={HOST}")
    en_historial = next((c for c in historial["courses"] if c["course_id"] == course_id), None)
    chk("AC-08 · si aparece en el historial", en_historial is not None)
    if en_historial:
        print(f"    historial: {en_historial['name']}  {en_historial['host_state']}  "
              f"{en_historial['students']} estudiante(s), "
              f"{en_historial['students_with_progress']} con progreso")

    # ── PASO 6 ───────────────────────────────────────────────────────────────
    titulo(6, "Juan vuelve a consultar")
    st, mis = call(f"/api/students/{JUAN}/courses/?host_id={HOST}")
    mio = next((c for c in mis["courses"] if c["course_id"] == course_id), None)
    chk("el curso sigue en su lista", mio is not None)
    if mio:
        print(f"    {mio['name']}")
        print(f"    progreso {mio['progress_pct']}%   estado: {mio['host_state']}")
        chk("installed=False", mio["installed"] is False)
        chk("available=False", mio["available"] is False)
        chk("AC-05 · conserva el progreso exacto", mio["progress_pct"] == progreso_antes,
            f"{mio['progress_pct']}% vs {progreso_antes}%")
        chk("aparece en la lista de NO disponibles",
            any(c["course_id"] == course_id for c in mis["unavailable"]))

    # ── PASO 7 ───────────────────────────────────────────────────────────────
    titulo(7, "Verificar en base de datos")
    st, curso = call(f"/api/courses/{course_id}/")
    chk("m05_curso EXISTE", st == 200, f"HTTP {st}")
    st, matriculas = call(f"/api/enrollments/?curso_id={course_id}")
    chk("m05_curso_estudiante EXISTE",
        any(m["persona_id"] == JUAN for m in matriculas), f"{len(matriculas)} fila(s)")
    st, avance = call(f"/api/students/{JUAN}/courses/{course_id}/progress/")
    chk("progreso de Juan EXISTE", avance["porcentaje"] == progreso_antes,
        f"{avance['porcentaje']}%")
    if nota_quiz is not None:
        # Si el quiz lo calificó el motor, la nota vive en m10_quiz_intento y el
        # desglose la trae. Si vino de un SCO o de una AU —que no transportan
        # preguntas— lo que persiste es el avance de la lección del quiz.
        con_nota = [x for x in avance["detalle"] if x["nota"]]
        quiz_lec = next(
            (x for x in avance["detalle"] if x["leccion_codigo"] == codigos[-1][0]), None
        )
        if con_nota:
            chk("nota del quiz EXISTE (calificada por el motor)", True,
                f"{con_nota[0]['nota']['puntaje']:.0f}/100")
        else:
            chk("nota del quiz EXISTE (como avance de su leccion)",
                quiz_lec is not None and quiz_lec["porcentaje"] == nota_quiz,
                f"{quiz_lec['porcentaje'] if quiz_lec else '?'}% == {nota_quiz}")
    st, filas = call(f"/api/course-hosts/?host_id={HOST}&curso_id={course_id}")
    chk("m05_curso_host.presente_local = 0",
        all(f["presente_local"] is False for f in filas), str(len(filas)) + " fila(s)")

    # ── PASO 8 ───────────────────────────────────────────────────────────────
    titulo(8, "Reinstalar el mismo paquete")
    cursos_antes = len(call("/api/courses/")[1])
    matriculas_antes = len(call("/api/enrollments/")[1])
    st, re = call("/api/course-packages/install/", {
        "package_base64": paquete_b64,
        "package_name": os.path.basename(zip_path),
        "host_id": HOST,
        "actor": "profesor-demo",
    })
    chk("reinstala sin error", st in (200, 201), f"HTTP {st}")
    if st not in (200, 201):
        print("  ", re)
        return 1
    print(f"    idempotente: {re['install']['idempotente']}")
    chk("presente_local = 1", re["host"]["presente_local"] is True)
    chk("disponible_estudiante = 1", re["host"]["disponible_estudiante"] is True)
    chk("retirado_en vuelve a NULL", re["host"]["retirado_en"] is None)
    chk("AC-10 · no duplico el curso",
        len(call("/api/courses/")[1]) == cursos_antes,
        f"{cursos_antes} -> {len(call('/api/courses/')[1])}")
    chk("AC-10 · no duplico la matricula",
        len(call("/api/enrollments/")[1]) == matriculas_antes,
        f"{matriculas_antes} -> {len(call('/api/enrollments/')[1])}")
    chk("AC-09 · es el mismo curso", re["install"]["course_id"] == course_id,
        re["install"]["course_id"])

    # ── PASO 9 ───────────────────────────────────────────────────────────────
    titulo(9, "Juan abre otra vez el curso")
    st, mis = call(f"/api/students/{JUAN}/courses/?host_id={HOST}")
    mio = next((c for c in mis["courses"] if c["course_id"] == course_id), None)
    chk("vuelve a estar disponible", mio and mio["available"] is True)
    print(f"    {mio['name']}")
    print(f"    progreso {mio['progress_pct']}%   estado: {mio['host_state']}")
    chk("EL CRITERIO DE EXITO · progreso identico al de antes",
        mio["progress_pct"] == progreso_antes,
        f"{mio['progress_pct']}% == {progreso_antes}%")

    st, avance = call(f"/api/students/{JUAN}/courses/{course_id}/progress/")
    print("\n    desglose tras reinstalar:")
    for x in avance["detalle"]:
        extra = f"  (nota {x['nota']['puntaje']:.0f}/{x['nota']['max_score']:.0f})" if x["nota"] else ""
        print(f"      {x['titulo'][:38]:<40} {x['porcentaje']:>6.2f}%  {x['estado']}{extra}")
    siguiente = next((x for x in avance["detalle"] if x["porcentaje"] < 100), None)
    if siguiente:
        print(f"\n    continuar desde: {siguiente['titulo']} ({siguiente['porcentaje']:.0f}%)")

    print()
    print("=" * 78)
    print(f"RESUMEN   {ok} correctas   {fail} fallas")
    print("=" * 78)
    return 1 if fail else 0


def _hacer_quiz(detalle_curso, course_id):
    """Responde el quiz del curso, si el paquete trajo uno con preguntas."""
    actividad = None
    for s in detalle_curso["secciones"]:
        for l in s["lecciones"]:
            for i in l["items"]:
                if i.get("actividad") and i["actividad"].get("activity_type") == "quiz":
                    actividad = i["actividad"]
    if actividad is None or not actividad.get("preguntas"):
        print("    (el paquete no trae un quiz con preguntas; el progreso se registra a mano)")
        return None

    st, intento = call("/api/quiz-attempts/start/", {
        "actividad_id": actividad["id"], "nombre_estudiante": "Juan",
        "persona_id": JUAN, "device_id": "tablet-juan"})
    if st not in (200, 201):
        print("    no se pudo iniciar el quiz:", intento)
        return None

    preguntas = sorted(actividad["preguntas"], key=lambda p: p["orden"])
    for n, p in enumerate(preguntas, start=1):
        opcion = p["opciones"][0]
        call("/api/quiz-attempts/answer/", {
            "intento_id": intento["id"], "pregunta_id": p["id"], "opcion_id": opcion["id"]})
    st, fin = call("/api/quiz-attempts/finish/", {"intento_id": intento["id"]})
    return float(fin["puntaje"]) if st == 200 else None


if __name__ == "__main__":
    sys.exit(main())
