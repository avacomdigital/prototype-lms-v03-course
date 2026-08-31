<#
.SYNOPSIS
    Ejecuta toda la batería de pruebas del prototipo: backend Django y librería .NET.

.DESCRIPTION
    - Backend: `manage.py test` sobre SQLite, sin necesidad de otro servicio.
      Cubre endpoints, serializers, integridad del modelo y consumidores de Channels.
    - .NET: pruebas xUnit de Avacom.OPS.Core (cliente HTTP, contratos de cursos,
      normalización de URL, red local y cliente WebSocket).

    Las cabezas MAUI (Student y Master) no se prueban aquí: requieren la carga de
    trabajo `maui` y un dispositivo o equipo Windows. Compílalas con:
        dotnet workload install maui
        dotnet build Avacom.OPS.slnx

.EXAMPLE
    .\scripts\Invoke-Tests.ps1

.EXAMPLE
    .\scripts\Invoke-Tests.ps1 -BackendOnly
#>
[CmdletBinding()]
param(
    [switch] $BackendOnly,
    [switch] $DotnetOnly,
    [string] $Python = ""
)

# Windows PowerShell 5.1 envuelve cada línea de stderr de un ejecutable nativo en un
# ErrorRecord. Con "Stop", el avance normal que Django escribe en stderr abortaría el
# script; el estado real se toma de $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$failures = @()

if ([string]::IsNullOrWhiteSpace($Python)) {
    $venv = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venv) { $Python = $venv } else { $Python = "python" }
}

if (-not $DotnetOnly) {
    Write-Host "== Pruebas del backend (Django + DRF + Channels, motor SQLite) ==" -ForegroundColor Cyan
    Push-Location (Join-Path $repositoryRoot "backend")
    try {
        $env:DB_ENGINE = "sqlite"
        $env:DJANGO_LOG_LEVEL = "WARNING"
        if (-not $env:DJANGO_SECRET_KEY) { $env:DJANGO_SECRET_KEY = "solo-para-pruebas" }
        & $Python manage.py test
        if ($LASTEXITCODE -ne 0) { $failures += "backend" }
    }
    finally {
        Pop-Location
        Remove-Item Env:DB_ENGINE -ErrorAction SilentlyContinue
        Remove-Item Env:DJANGO_LOG_LEVEL -ErrorAction SilentlyContinue
    }
    Write-Host ""
}

if (-not $BackendOnly) {
    Write-Host "== Pruebas de Avacom.OPS.Core (xUnit) ==" -ForegroundColor Cyan
    $project = Join-Path $repositoryRoot "tests\Avacom.OPS.Core.Tests\Avacom.OPS.Core.Tests.csproj"
    & dotnet test $project --nologo
    if ($LASTEXITCODE -ne 0) { $failures += "dotnet" }
    Write-Host ""
}

if ($failures.Count -gt 0) {
    Write-Host "Fallaron: $($failures -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "Todas las pruebas pasaron." -ForegroundColor Green
