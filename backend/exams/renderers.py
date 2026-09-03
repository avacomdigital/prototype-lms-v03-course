"""
El renderizador JSON de la API, declarando su codificación.

DRF deja `charset = None` en su JSONRenderer porque el RFC 8259 ya obliga a que
el JSON sea UTF-8, así que el parámetro es redundante. En teoría. En la práctica
un cliente que recibe `application/json` a secas tiene que adivinar, y hay
clientes muy usados que adivinan mal:

    PS> (Invoke-RestMethod .../api/courses/)[0].titulo
    ExploraciÃ³n del medio

Windows PowerShell 5.1 cae a Latin-1 cuando no hay charset. El coste de
declararlo son veinte caracteres por respuesta; el de no declararlo es que los
acentos lleguen rotos a cualquiera que consuma la API con una herramienta que no
controlamos.
"""

from rest_framework.renderers import JSONRenderer


class JSONRendererUtf8(JSONRenderer):
    charset = "utf-8"
