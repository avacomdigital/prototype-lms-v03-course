<#
.SYNOPSIS
    Levanta la API del Master (Daphne) de forma nativa, sin Docker.

.DESCRIPTION
    Reemplaza a `docker compose up`. Lee el puerto de API_PORT en el .env y avisa
    antes de arrancar si ese puerto ya está ocupado por otro programa, que es el
    fallo más común en un equipo Windows de uso general.

    Se queda en primer plano sirviendo los cursos. Ciérralo con Ctrl+C.

.PARAMETER Port
    Fuerza un puerto distinto al de API_PORT del .env.

.PARAMETER LocalOnly
    Escucha sólo en 127.0.0.1. Útil para probar en el propio Master sin exponer
    nada a la LAN. Sin este parámetro escucha en todas las interfaces, que es lo
    que necesitan los dispositivos de los estudiantes.

.EXAMPLE
    .\scripts\windows\Start-Backend.ps1
    Sirve el catálogo y el quiz a la LAN en el puerto del .env.

.EXAMPLE
    .\scripts\windows\Start-Backend.ps1 -LocalOnly -Port 8100
    Prueba local en el puerto 8100.
#>
[CmdletBinding()]
param(
    [int] $Port = 0,
    [switch] $LocalOnly
)

$ErrorActionPreference = "Continue"

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backend = Join-Path $repositoryRoot "backend"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $repositoryRoot ".env"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "No existe el entorno virtual. Ejecuta primero: .\scripts\windows\Install-Backend.ps1"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "No existe el archivo .env. Ejecuta primero: .\scripts\windows\Install-Backend.ps1"
}

# Puerto: el parámetro manda sobre API_PORT del .env.
if ($Port -eq 0) {
    $Port = 8000
    Get-Content -LiteralPath $envFile | ForEach-Object {
        if ($_ -match "^\s*API_PORT\s*=\s*(\d+)") { $Port = [int]$Matches[1] }
    }
}

$bind = if ($LocalOnly) { "127.0.0.1" } else { "0.0.0.0" }

# El puerto ocupado produce un WinError 10013 poco descriptivo en Daphne, así que
# se detecta antes y se dice quién lo tiene.
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $owners = $busy.OwningProcess | Sort-Object -Unique | ForEach-Object {
        $process = Get-Process -Id $_ -ErrorAction SilentlyContinue
        if ($process) { "$($process.ProcessName) (PID $_)" } else { "PID $_" }
    }
    Write-Host "El puerto $Port ya está ocupado por: $($owners -join ', ')" -ForegroundColor Red
    Write-Host "Cambia API_PORT en el .env o arranca con -Port <otro>." -ForegroundColor Yellow
    Write-Host "Recuerda que los dispositivos deben apuntar al mismo puerto." -ForegroundColor Yellow
    exit 1
}

# IP de LAN, para copiarla tal cual en la pantalla de registro del estudiante.
$lanAddress = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host "AVACOM OPS Master - API" -ForegroundColor Cyan
Write-Host "   Escuchando en   ${bind}:$Port"
Write-Host "   Salud local     http://127.0.0.1:$Port/health/"
if ($lanAddress -and -not $LocalOnly) {
    Write-Host "   Para los estudiantes: http://${lanAddress}:$Port/" -ForegroundColor Green
    Write-Host "   Si no responde desde otro equipo, abre el puerto:" -ForegroundColor Yellow
    Write-Host "      .\scripts\windows\Open-MasterFirewall.ps1 -Port $Port" -ForegroundColor Yellow
}
Write-Host "   Ctrl+C para detener."
Write-Host ""

Push-Location $backend
try {
    & $venvPython -m daphne -b $bind -p $Port exam_master.asgi:application
}
finally { Pop-Location }
