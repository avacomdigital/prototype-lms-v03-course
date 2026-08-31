"""
Construye matematicas6.zip: un paquete SCORM 2004 real para el escenario del §21.

Se genera con un script en vez de versionar un binario para que quede a la vista
QUÉ contiene el paquete y se pueda regenerar o modificar. Produce también un
gemelo en CMI5 (matematicas6_cmi5.zip), que sirve para demostrar el AC-11: la
lógica de m05_curso_host funciona igual con los dos formatos.

Uso:
    python packages/construir_matematicas6.py
    python packages/construir_matematicas6.py --salida C:\\ruta
"""

import argparse
import os
import zipfile

IMSMANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="AVACOM-MAT6" version="2.0"
          xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
          xmlns:imsss="http://www.imsglobal.org/xsd/imsss">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>

  <organizations default="ORG-MAT6">
    <organization identifier="ORG-MAT6">
      <title>Matematicas 6</title>

      <item identifier="SEC-FRACCIONES">
        <title>Fracciones</title>

        <item identifier="LESSON-CONCEPTO">
          <title>Leccion 1 - Concepto de fraccion</title>
          <item identifier="ITEM-LEC-CONCEPTO" identifierref="RES-LECTURA-CONCEPTO">
            <title>Lectura - Que es una fraccion</title>
          </item>
          <item identifier="ITEM-VID-CONCEPTO" identifierref="RES-VIDEO-CONCEPTO">
            <title>Video - Fracciones en la vida diaria</title>
          </item>
        </item>

        <item identifier="LESSON-EQUIVALENTES">
          <title>Leccion 2 - Fracciones equivalentes</title>
          <item identifier="ITEM-LEC-EQUIV" identifierref="RES-LECTURA-EQUIV">
            <title>Lectura - Amplificar y simplificar</title>
          </item>
        </item>

        <item identifier="LESSON-SUMA">
          <title>Leccion 3 - Suma y resta</title>
          <item identifier="ITEM-VID-SUMA" identifierref="RES-VIDEO-SUMA">
            <title>Video - Denominadores distintos</title>
          </item>
        </item>
      </item>

      <item identifier="SEC-EVALUACION">
        <title>Evaluacion</title>
        <item identifier="LESSON-QUIZ">
          <title>Leccion 4 - Quiz de la unidad</title>
          <item identifier="ITEM-QUIZ" identifierref="RES-QUIZ">
            <title>Quiz de fracciones</title>
          </item>
        </item>
      </item>
    </organization>
  </organizations>

  <resources>
    <resource identifier="RES-LECTURA-CONCEPTO" type="webcontent"
              adlcp:scormType="asset" href="contenido/concepto.html">
      <file href="contenido/concepto.html"/>
    </resource>
    <resource identifier="RES-VIDEO-CONCEPTO" type="webcontent"
              adlcp:scormType="asset" href="contenido/fracciones.mp4">
      <file href="contenido/fracciones.mp4"/>
    </resource>
    <resource identifier="RES-LECTURA-EQUIV" type="webcontent"
              adlcp:scormType="asset" href="contenido/equivalentes.html">
      <file href="contenido/equivalentes.html"/>
    </resource>
    <resource identifier="RES-VIDEO-SUMA" type="webcontent"
              adlcp:scormType="asset" href="contenido/suma.mp4">
      <file href="contenido/suma.mp4"/>
    </resource>
    <resource identifier="RES-QUIZ" type="webcontent"
              adlcp:scormType="sco" href="quiz/index.html">
      <file href="quiz/index.html"/>
    </resource>
  </resources>
</manifest>
"""

CMI5 = """<?xml version="1.0" encoding="UTF-8"?>
<courseStructure xmlns="https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd">
  <course id="https://avacom.edu/courses/matematicas-6">
    <title><langstring lang="es">Matematicas 6</langstring></title>
    <description><langstring lang="es">Fracciones y evaluacion de la unidad.</langstring></description>
  </course>

  <block id="https://avacom.edu/blocks/mat6/fracciones">
    <title><langstring lang="es">Fracciones</langstring></title>

    <block id="https://avacom.edu/blocks/mat6/concepto">
      <title><langstring lang="es">Leccion 1 - Concepto de fraccion</langstring></title>
      <au id="https://avacom.edu/au/mat6/concepto-lectura" moveOn="Completed"
          url="contenido/concepto.html">
        <title><langstring lang="es">Lectura - Que es una fraccion</langstring></title>
      </au>
    </block>

    <block id="https://avacom.edu/blocks/mat6/equivalentes">
      <title><langstring lang="es">Leccion 2 - Fracciones equivalentes</langstring></title>
      <au id="https://avacom.edu/au/mat6/equivalentes" moveOn="CompletedOrPassed"
          masteryScore="0.7" url="contenido/equivalentes.html">
        <title><langstring lang="es">Amplificar y simplificar</langstring></title>
      </au>
    </block>

    <block id="https://avacom.edu/blocks/mat6/suma">
      <title><langstring lang="es">Leccion 3 - Suma y resta</langstring></title>
      <au id="https://avacom.edu/au/mat6/suma" moveOn="Completed" url="contenido/suma.html">
        <title><langstring lang="es">Denominadores distintos</langstring></title>
      </au>
    </block>
  </block>

  <block id="https://avacom.edu/blocks/mat6/evaluacion">
    <title><langstring lang="es">Evaluacion</langstring></title>
    <au id="https://avacom.edu/au/mat6/quiz" moveOn="Passed" masteryScore="0.8"
        url="quiz/index.html">
      <title><langstring lang="es">Leccion 4 - Quiz de la unidad</langstring></title>
    </au>
  </block>
</courseStructure>
"""

# Contenido de relleno. El binario pesado no vive en la base: el paquete solo
# necesita traer los archivos a los que apunta el descriptor.
ARCHIVOS = {
    "contenido/concepto.html": "<h1>Que es una fraccion</h1><p>Parte de un todo.</p>",
    "contenido/equivalentes.html": "<h1>Fracciones equivalentes</h1><p>1/2 = 2/4.</p>",
    "contenido/suma.html": "<h1>Suma y resta</h1><p>Homogeneizar denominadores.</p>",
    "contenido/fracciones.mp4": "video de relleno",
    "contenido/suma.mp4": "video de relleno",
    "quiz/index.html": "<h1>Quiz de fracciones</h1>",
}


def construir(ruta, descriptor_nombre, descriptor_xml):
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    # ZIP_STORED y date_time fija: el mismo contenido produce el MISMO byte a
    # byte, y por lo tanto la misma huella SHA-256. Sin eso, reinstalar el
    # "mismo" paquete daria otra huella y la deteccion de reinstalacion fallaria.
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        entradas = [(descriptor_nombre, descriptor_xml)] + sorted(ARCHIVOS.items())
        for nombre, texto in entradas:
            info = zipfile.ZipInfo(nombre, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, texto)
    return os.path.getsize(ruta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", default=os.path.dirname(os.path.abspath(__file__)))
    args = parser.parse_args()

    scorm = os.path.join(args.salida, "matematicas6.zip")
    cmi5 = os.path.join(args.salida, "matematicas6_cmi5.zip")

    n1 = construir(scorm, "imsmanifest.xml", IMSMANIFEST)
    n2 = construir(cmi5, "cmi5.xml", CMI5)

    print(f"SCORM 2004  {scorm}  ({n1:,} bytes)")
    print("            organization ORG-MAT6 · 2 secciones · 4 lecciones · 5 recursos (1 SCO)")
    print(f"CMI5        {cmi5}  ({n2:,} bytes)")
    print("            course https://avacom.edu/courses/matematicas-6· 2 bloques · 4 AU")


if __name__ == "__main__":
    main()
