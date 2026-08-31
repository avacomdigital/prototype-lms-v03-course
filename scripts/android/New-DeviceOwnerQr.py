"""Genera el QR de aprovisionamiento Device Owner para las tabletas del examen.

El QR se escanea en la PRIMERA pantalla del asistente de Android recién restablecido
(tocándola seis veces). Android descarga el APK de la URL indicada, verifica su
checksum y deja la aplicación como Device Owner, sin cable y sin adb.

Uso desde la raíz del repositorio:

    .venv\\Scripts\\python scripts\\android\\New-DeviceOwnerQr.py ^
        --apk dist\\AvacomStudent-arm64.apk ^
        --host 192.168.0.34 --port 8080

Con credenciales de Wi-Fi, para que la tableta se conecte sola durante el asistente:

    ... --wifi-ssid Makers --wifi-password LA_CLAVE

Sin ellas, hay que conectar la Wi-Fi a mano en el asistente antes de escanear.
Requiere: pip install "qrcode[pil]"
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import sys

COMPONENT = "com.avacom.student/com.avacom.student.ExamDeviceAdminReceiver"


def package_checksum(apk: pathlib.Path) -> str:
    """SHA-256 en Base64 URL-safe sin relleno, el formato que exige Android."""
    digest = hashlib.sha256(apk.read_bytes()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_payload(args, checksum: str) -> dict:
    url = f"http://{args.host}:{args.port}/{args.apk_name}"
    payload = {
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": COMPONENT,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": url,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM": checksum,
        "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": False,
        # Dejar las apps del sistema deshabilitadas reduce lo que el estudiante puede
        # abrir si el Lock Task fallara.
        "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": False,
        "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {"deployment": "exam-lab"},
    }
    if args.wifi_ssid:
        payload["android.app.extra.PROVISIONING_WIFI_SSID"] = args.wifi_ssid
        if args.wifi_password:
            payload["android.app.extra.PROVISIONING_WIFI_PASSWORD"] = args.wifi_password
            payload["android.app.extra.PROVISIONING_WIFI_SECURITY_TYPE"] = "WPA"
        else:
            payload["android.app.extra.PROVISIONING_WIFI_SECURITY_TYPE"] = "NONE"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", required=True, help="Ruta al APK firmado")
    parser.add_argument("--host", required=True, help="IP de LAN del Master que sirve el APK")
    parser.add_argument("--port", type=int, default=8080, help="Puerto del servidor HTTP (8080)")
    parser.add_argument("--wifi-ssid", help="SSID para que la tableta se conecte durante el asistente")
    parser.add_argument("--wifi-password", help="Clave del SSID. Se incrusta en el QR: trátalo como un secreto")
    parser.add_argument("--out-dir", default="dist", help="Carpeta de salida (dist)")
    args = parser.parse_args()

    apk = pathlib.Path(args.apk)
    if not apk.is_file():
        print(f"No existe el APK: {apk}", file=sys.stderr)
        return 1
    args.apk_name = apk.name

    checksum = package_checksum(apk)
    payload = build_payload(args, checksum)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "device-owner-qr.json"
    png_path = out_dir / "device-owner-qr.png"

    # separators sin espacios: el QR es más pequeño y por tanto más fácil de escanear.
    texto = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    json_path.write_text(texto, encoding="utf-8")

    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(texto)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(png_path)

    print(f"APK        : {apk} ({apk.stat().st_size / 1_048_576:.1f} MB)")
    print(f"Checksum   : {checksum}")
    print(f"Descarga   : {payload['android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION']}")
    print(f"Wi-Fi      : {args.wifi_ssid or '(hay que conectarla a mano en el asistente)'}")
    print(f"JSON       : {json_path}")
    print(f"QR         : {png_path}  ({qr.version=}, {len(texto)} caracteres)")
    print()
    print("Sirve el APK antes de escanear:")
    print(f"  .venv\\Scripts\\python -m http.server {args.port} --directory {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
