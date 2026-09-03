<#
.SYNOPSIS
    Detiene y elimina AVACOMOPSBackend al desinstalar.

.DESCRIPTION
    Lo ejecuta el desinstalador. Toca EXCLUSIVAMENTE el servicio de OPS Master,
    por su nombre exacto: si AVACOM Biblioteca tiene servicios propios en el
    mismo equipo, este script no los ve ni los enumera.

    No falla si el servicio no está: desinstalar dos veces, o desinstalar una
    instalación donde el servicio nunca llegó a crearse, tiene que terminar
    limpio igual.
#>
[CmdletBinding()]
param(
    [string] $Nombre = "AVACOMOPSBackend",
    [switch] $Silencioso
)

$ErrorActionPreference = "Continue"

function Decir([string] $texto) { if (-not $Silencioso) { Write-Host $texto } }

$servicio = Get-Service -Name $Nombre -ErrorAction SilentlyContinue
if (-not $servicio) {
    Decir "El servicio $Nombre no esta registrado. Nada que quitar."
    exit 0
}

if ($servicio.Status -ne "Stopped") {
    Decir "Deteniendo $Nombre"
    Stop-Service -Name $Nombre -Force -ErrorAction SilentlyContinue
    $limite = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $limite) {
        $actual = Get-Service -Name $Nombre -ErrorAction SilentlyContinue
        if (-not $actual -or $actual.Status -eq "Stopped") { break }
        Start-Sleep -Milliseconds 500
    }
}

# El servicio cierra daphne y sus hijos al detenerse. Se comprueba que el puerto
# quedo libre porque un daphne huerfano dejaria el 8000 ocupado y la siguiente
# instalacion fallaria la validacion sin motivo aparente.
$limite = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $limite) {
    $ocupado = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
    if ($ocupado.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
}

Decir "Eliminando el servicio $Nombre"
& sc.exe delete $Nombre | Out-Null

# sc.exe delete marca el servicio para borrado; desaparece cuando se cierra el
# ultimo manejador. Se espera un momento para que una reinstalacion inmediata no
# choque con "el servicio esta marcado para eliminacion".
Start-Sleep -Seconds 2
exit 0
