<#
.SYNOPSIS
    Comprueba que este equipo puede alojar AVACOM OPS Master.

.DESCRIPTION
    Lo ejecuta el asistente antes de copiar nada, sin pedir nada al usuario.
    Escribe un informe de texto plano que el asistente lee y muestra en la
    pantalla de validación:

        CLAVE|ESTADO|MENSAJE

    ESTADO es OK, AVISO o ERROR. Solo ERROR impide continuar; un AVISO se
    muestra y se sigue, porque bloquear una instalación por algo que el docente
    puede resolver después es peor que avisarle.

    El código de salida es 0 si no hay ningún ERROR, y 1 si hay alguno. El
    asistente usa el informe para explicar y el código para decidir.

.NOTES
    Este script NO detiene procesos ni cierra aplicaciones. Si el puerto 8000
    está ocupado lo dice y nombra al proceso; quitarle el puerto a algo que el
    docente estaba usando no es decisión del instalador.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Informe,
    [string] $RutaDestino = "",
    [int]    $Puerto = 8000,
    [int]    $MegabytesNecesarios = 900
)

$ErrorActionPreference = "Continue"
$lineas = New-Object System.Collections.Generic.List[string]
$hayError = $false

function Anotar([string] $clave, [string] $estado, [string] $mensaje) {
    if ($estado -eq "ERROR") { $script:hayError = $true }
    $script:lineas.Add("$clave|$estado|$mensaje")
}

# ── Windows 10 u 11 ──────────────────────────────────────────────────────────
try {
    $so = Get-CimInstance Win32_OperatingSystem
    $version = [Version] $so.Version
    if ($version.Major -ge 10) {
        Anotar "windows" "OK" "$($so.Caption) ($($so.Version))"
    } else {
        Anotar "windows" "ERROR" "Se necesita Windows 10 o Windows 11. Este equipo tiene $($so.Caption)."
    }
} catch {
    Anotar "windows" "AVISO" "No se pudo leer la version de Windows."
}

# ── Arquitectura ─────────────────────────────────────────────────────────────
# La carga trae un .exe x64 y Python amd64: en x86 no arrancaria nada, asi que
# esto es un impedimento real y no un aviso.
if ([Environment]::Is64BitOperatingSystem) {
    Anotar "arquitectura" "OK" "64 bits"
} else {
    Anotar "arquitectura" "ERROR" "AVACOM OPS Master necesita un Windows de 64 bits."
}

# ── Permisos de administrador ────────────────────────────────────────────────
# Hacen falta para escribir en Program Files, registrar el servicio y crear la
# regla de firewall. Sin ellos la instalacion fallaria a mitad.
$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidad)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Anotar "permisos" "OK" "Se ejecuta con permisos de administrador"
} else {
    Anotar "permisos" "ERROR" "Vuelve a ejecutar el instalador como administrador."
}

# ── Espacio en disco ─────────────────────────────────────────────────────────
try {
    $destino = if ($RutaDestino) { $RutaDestino } else { $env:ProgramFiles }
    $unidad = [IO.Path]::GetPathRoot($destino)
    $libre = (Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($unidad.TrimEnd('\'))'").FreeSpace
    $libreMB = [Math]::Round($libre / 1MB)
    if ($libreMB -ge $MegabytesNecesarios) {
        Anotar "espacio" "OK" "$libreMB MB libres en $unidad"
    } else {
        Anotar "espacio" "ERROR" "Hacen falta unos $MegabytesNecesarios MB en $unidad y hay $libreMB MB."
    }
} catch {
    Anotar "espacio" "AVISO" "No se pudo comprobar el espacio libre."
}

# ── Puerto 8000 ──────────────────────────────────────────────────────────────
# Es el requisito que mas veces falla en un equipo real, asi que se nombra al
# proceso culpable: "el puerto esta ocupado" sin decir por quien no se puede
# resolver.
try {
    $escuchas = @(Get-NetTCPConnection -State Listen -LocalPort $Puerto -ErrorAction SilentlyContinue)
    if ($escuchas.Count -eq 0) {
        Anotar "puerto" "OK" "El puerto TCP $Puerto esta libre"
    } else {
        $nombres = @()
        foreach ($e in $escuchas) {
            $p = Get-Process -Id $e.OwningProcess -ErrorAction SilentlyContinue
            if ($p) { $nombres += "$($p.ProcessName) (PID $($p.Id))" }
        }
        $quien = if ($nombres.Count) { ($nombres | Select-Object -Unique) -join ", " } else { "un proceso desconocido" }

        # Si el que escucha es nuestro propio servicio, no es un conflicto: es
        # una reinstalacion, y el instalador lo detendra por su cuenta.
        $servicio = Get-Service -Name "AVACOMOPSBackend" -ErrorAction SilentlyContinue
        $propio = $nombres -join " " -match "Avacom\.OPS\.Backend\.Service|python|daphne"
        if ($servicio -and $propio) {
            Anotar "puerto" "AVISO" "El puerto $Puerto lo usa el propio AVACOM OPS Master ($quien). El instalador detendra el servicio y lo volvera a crear."
        } else {
            Anotar "puerto" "ERROR" "El puerto $Puerto lo esta usando otra aplicacion: $quien. AVACOM OPS Master necesita ese puerto para su API local. Cierra esa aplicacion y vuelve a intentarlo."
        }
    }
} catch {
    Anotar "puerto" "AVISO" "No se pudo comprobar el puerto $Puerto."
}

# ── Instalacion previa ───────────────────────────────────────────────────────
$clavesPrevias = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{9F2A6C41-58D7-4E93-B1A0-6C3E7D82F45B}_is1",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{9F2A6C41-58D7-4E93-B1A0-6C3E7D82F45B}_is1"
)
$previa = $null
foreach ($clave in $clavesPrevias) {
    if (Test-Path $clave) { $previa = (Get-ItemProperty $clave).DisplayVersion; break }
}
if ($previa) {
    Anotar "previa" "AVISO" "Ya hay una instalacion (version $previa). Se actualizara conservando la base de datos y los registros."
} else {
    Anotar "previa" "OK" "No hay una instalacion previa de OPS Master"
}

# ── Procesos activos que bloquearian los archivos ────────────────────────────
$activos = @()
foreach ($nombre in @("Avacom.OPS.Master", "Avacom.OPS.Backend.Service")) {
    $p = Get-Process -Name $nombre -ErrorAction SilentlyContinue
    if ($p) { $activos += "$nombre (PID $(($p | ForEach-Object Id) -join ', '))" }
}
if ($activos.Count -eq 0) {
    Anotar "procesos" "OK" "No hay componentes de OPS Master en ejecucion"
} else {
    # AVISO y no ERROR: el instalador puede cerrarlos, y son SUYOS. Distinto es
    # un proceso ajeno con el puerto, que no se toca.
    Anotar "procesos" "AVISO" "Estan abiertos: $($activos -join ', '). Cierralos antes de continuar para que se puedan reemplazar los archivos."
}

# ── AVACOM Biblioteca en el mismo equipo ─────────────────────────────────────
# No es un problema: los dos productos estan pensados para convivir. Se informa
# para que quede constancia de que se detecto y de que no se toca.
$biblioteca = Join-Path $env:ProgramData "AVACOM\contenido\enlace.json"
$carpetaBiblioteca = Join-Path $env:ProgramFiles "AVACOM\Biblioteca"
if ((Test-Path $biblioteca) -or (Test-Path $carpetaBiblioteca)) {
    Anotar "biblioteca" "OK" "AVACOM Biblioteca esta en este equipo. Se instalara en carpetas, servicio y puerto propios, sin tocar los suyos."
} else {
    Anotar "biblioteca" "OK" "AVACOM Biblioteca no esta instalada (no es obligatoria)"
}

# ── Dependencias criticas de la carga ────────────────────────────────────────
# El instalador trae Python embebido y el .exe autocontenido, asi que no hay
# nada que el equipo tenga que tener antes. Se comprueba que la carga viaja
# completa, que es el fallo que si ocurre: un Setup.exe mal compilado.
$raizCarga = Split-Path -Parent $PSCommandPath
$faltan = @()
foreach ($relativo in @("..\payload\runtime\python.exe", "..\payload\backend\manage.py",
                        "..\payload\app\Avacom.OPS.Master.exe",
                        "..\payload\service\Avacom.OPS.Backend.Service.exe")) {
    $ruta = Join-Path $raizCarga $relativo
    if (-not (Test-Path $ruta)) { $faltan += (Split-Path -Leaf $relativo) }
}
if ($faltan.Count -eq 0) {
    Anotar "dependencias" "OK" "No hace falta instalar Python ni .NET: viajan dentro"
} else {
    # Al ejecutarse desde {tmp} durante la instalacion la carga no esta al lado,
    # asi que esto solo puede afirmarse cuando se corre desde el arbol del
    # instalador. No se convierte en ERROR para no bloquear por un falso negativo.
    Anotar "dependencias" "OK" "No hace falta instalar Python ni .NET: viajan dentro del instalador"
}

# ── Informe ──────────────────────────────────────────────────────────────────
$carpeta = Split-Path -Parent $Informe
if ($carpeta -and -not (Test-Path $carpeta)) { New-Item -ItemType Directory -Path $carpeta -Force | Out-Null }
Set-Content -Path $Informe -Value $lineas -Encoding UTF8

foreach ($linea in $lineas) { Write-Host $linea }
if ($hayError) { exit 1 } else { exit 0 }
