<#
.SYNOPSIS
    Registra y arranca AVACOMOPSBackend, el servicio que mantiene viva la API.

.DESCRIPTION
    Lo ejecuta el asistente al final de la instalación, sin pedir nada.

    Por qué un servicio y no dejar que el panel levante la API: hasta ahora las
    tabletas solo tenían servicio mientras alguien tuviera abierta la aplicación
    del profesor. Un aula no funciona así. Con el servicio en Automático la API
    escucha desde que arranca Windows, y el panel pasa a ser un cliente más.

    Convivencia con AVACOM Biblioteca: el nombre del servicio, su descripción y
    su carpeta son propios. Este script NO enumera ni toca servicios ajenos.

.NOTES
    Idempotente. Si el servicio ya existe se reconfigura en vez de fallar, que
    es lo que ocurre en una reinstalación.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $RutaEjecutable,
    [string] $Nombre = "AVACOMOPSBackend",
    [string] $Etiqueta = "AVACOM OPS Master Backend",
    [int]    $Puerto = 8000,
    [int]    $SegundosDeEspera = 60
)

$ErrorActionPreference = "Stop"

function Paso([string] $texto) { Write-Host "== $texto" }

if (-not (Test-Path $RutaEjecutable)) {
    throw "No se encontro el ejecutable del servicio en $RutaEjecutable"
}

# ── 1 · si ya existe, se detiene antes de reconfigurarlo ─────────────────────
$existente = Get-Service -Name $Nombre -ErrorAction SilentlyContinue
if ($existente) {
    Paso "El servicio ya existe; se detiene para reconfigurarlo"
    if ($existente.Status -ne "Stopped") {
        Stop-Service -Name $Nombre -Force -ErrorAction SilentlyContinue
        # Se espera de verdad: sc.exe config sobre un servicio que aun se esta
        # deteniendo deja la configuracion a medias.
        $limite = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $limite) {
            if ((Get-Service -Name $Nombre).Status -eq "Stopped") { break }
            Start-Sleep -Milliseconds 500
        }
    }
    & sc.exe config $Nombre binPath= "`"$RutaEjecutable`"" start= auto | Out-Null
}
else {
    Paso "Creando el servicio $Nombre"
    # LocalSystem: el servicio tiene que poder escribir en ProgramData y enlazar
    # el puerto antes de que ningun usuario inicie sesion.
    & sc.exe create $Nombre binPath= "`"$RutaEjecutable`"" DisplayName= "$Etiqueta" start= auto obj= "LocalSystem" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "sc.exe create devolvio $LASTEXITCODE" }
}

& sc.exe description $Nombre "Mantiene la API local de AVACOM OPS Master escuchando en 0.0.0.0:$Puerto para las tabletas del aula. No interfiere con AVACOM Biblioteca." | Out-Null

# ── 2 · recuperacion automatica ──────────────────────────────────────────────
# Si el proceso muere, Windows lo reinicia. El servicio ya reintenta por su
# cuenta, pero esto cubre el caso de que muera el propio servicio.
& sc.exe failure $Nombre reset= 300 actions= restart/5000/restart/15000/restart/60000 | Out-Null

# ── 3 · arrancar ─────────────────────────────────────────────────────────────
Paso "Arrancando el servicio"
Start-Service -Name $Nombre -ErrorAction Stop

# ── 4 · comprobar que la API quedo operativa ─────────────────────────────────
# Que el servicio este "Running" no basta: el servicio arranca aunque daphne
# muera al importar Django. Lo que decide si el aula tiene API es /health/.
Paso "Comprobando http://127.0.0.1:$Puerto/health/"
$operativa = $false
$limite = (Get-Date).AddSeconds($SegundosDeEspera)
while ((Get-Date) -lt $limite) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health/" -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -eq 200) { $operativa = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

$estado = (Get-Service -Name $Nombre).Status
if ($operativa) {
    Write-Host "SERVICIO=$estado"
    Write-Host "API=OK"
    exit 0
}

# No se lanza una excepcion: la instalacion ya copio todo y el servicio existe.
# Se informa para que el asistente lo diga en la ultima pantalla, en vez de
# terminar en verde mintiendo.
Write-Host "SERVICIO=$estado"
Write-Host "API=SIN_RESPUESTA"
exit 2
