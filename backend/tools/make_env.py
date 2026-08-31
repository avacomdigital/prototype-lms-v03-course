"""Genera el archivo .env de una instalación de AVACOM OPS Core.

Lo ejecuta el instalador wizard con el Python embebido que él mismo copia. La
clave se genera aquí, y no en el script del instalador, por dos razones:

- El Pascal Script de Inno Setup ofrece `Random`, pensado para sorteos y no para
  material criptográfico. DJANGO_SECRET_KEY firma las sesiones y las cookies de
  la API, así que se deriva de `secrets`, que sí usa la fuente de entropía del
  sistema operativo.
- Incrustar una clave fija en el Setup.exe haría que todas las sedes compartieran
  la misma. Generarla por instalación evita que comprometer un equipo comprometa
  al resto.

Un .env ya existente NUNCA se sobrescribe: puede llevar ajustes de la sede, y
cambiar la clave invalidaría las sesiones abiertas.

Uso:
    python tools/make_env.py <ruta-del-.env> [puerto] [carpeta-de-datos]
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

DEFAULT_PORT = "8000"


def build(port: str, data_dir: str) -> str:
    return "\n".join(
        [
            "# Generado por el instalador de AVACOM OPS Core",
            f"DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}",
            "DJANGO_DEBUG=0",
            "DJANGO_ALLOWED_HOSTS=*",
            "DJANGO_LOG_LEVEL=INFO",
            # SQLite a propósito: el equipo del profesor no debe requerir MongoDB
            # ni Docker para levantar la API.
            "DB_ENGINE=sqlite",
            f"API_PORT={port}",
            # Carpeta escribible para la base y los registros. El codigo se instala
            # en Program Files, donde un usuario estandar no puede escribir, y sin
            # esto la API moria al arrancar intentando crear su carpeta de logs.
            f"AVACOM_DATA_DIR={data_dir}",
        ]
    ) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: make_env.py <ruta-del-.env> [puerto] [carpeta-de-datos]", file=sys.stderr)
        return 2

    target = Path(argv[1])
    port = argv[2] if len(argv) > 2 else DEFAULT_PORT
    # Sin tercer argumento se deja junto a la API, que es lo util en desarrollo.
    data_dir = argv[3] if len(argv) > 3 else str(Path(__file__).resolve().parent.parent)

    if target.is_file():
        return upgrade(target, port, data_dir)

    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" explícito: python-dotenv acepta ambos finales de línea, pero
    # así el archivo es idéntico al que se genera en cualquier otra plataforma.
    target.write_text(build(port, data_dir), encoding="utf-8", newline="\n")
    print(f".env creado: {target} (datos en {data_dir})")
    return 0


def upgrade(target: Path, port: str, data_dir: str) -> int:
    """Añade a un .env existente las claves que le falten, sin tocar las que ya tiene.

    Conservar el .env entre versiones es correcto: puede llevar ajustes de la sede
    que no hay que pisar. Pero dejarlo intacto sin más es un error, y costó un
    despliegue: al aparecer AVACOM_DATA_DIR en una versión nueva, un .env anterior
    seguía sin esa clave, `settings.py` caía a su valor por omisión —la carpeta de
    la propia API, dentro de Program Files— y la base quedaba en una ruta de solo
    lectura. La API arrancaba y respondía 500 en cuanto tocaba la base.

    Sólo se AÑADE lo que falta. Nunca se cambia un valor existente de la sede.
    """
    text = target.read_text(encoding="utf-8")
    present = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    required = dict(
        line.split("=", 1) for line in build(port, data_dir).splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    missing = {key: value for key, value in required.items() if key not in present}

    if not missing:
        print(f".env existente ya completo: {target}")
        return 0

    addition = "\n".join(
        ["", f"# Claves añadidas al actualizar ({len(missing)}); las anteriores se conservan."]
        + [f"{key}={value}" for key, value in missing.items()]
    ) + "\n"

    if not text.endswith("\n"):
        addition = "\n" + addition
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(addition)

    print(f".env actualizado: {target} · añadidas {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
