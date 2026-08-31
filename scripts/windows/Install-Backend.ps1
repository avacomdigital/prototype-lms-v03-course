<#
.SYNOPSIS
    Instala la API local de cursos en Windows, con SQLite y sin Docker.

.DESCRIPTION
    Verifica Python 3.12+, crea .venv, instala DRF/Channels/Daphne, genera un
    .env propio, aplica las migraciones y carga Álgebra Octavo B con su quiz.
    Es idempotente: puede ejecutarse de nuevo sin duplicar el curso demo.

.PARAMETER IncludeDevDependencies
    Instala además el cliente WebSocket usado por Invoke-EndpointProof.ps1.

.EXAMPLE
    .\scripts\windows\Install-Backend.ps1 -IncludeDevDependencies
#>
[CmdletBinding()]
param(
    [switch] $IncludeDevDependencies,
    [string] $Python = "python"
)

$ErrorActionPreference = "Continue"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backend = Join-Path $repositoryRoot "backend"
$venv = Join-Path $repositoryRoot ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$envFile = Join-Path $repositoryRoot ".env"

function Step($text) { Write-Host "`n== $text ==" -ForegroundColor Cyan }
function Ok($text) { Write-Host "   $text" -ForegroundColor Green }

Step "Comprobando Python"
$version = & $Python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "No se encontró Python. Instala Python 3.12 o superior y agrégalo al PATH."
}
if ($version -notmatch "Python (\d+)\.(\d+)") { throw "No se pudo interpretar la versión: $version" }
if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 12)) {
    throw "Se requiere Python 3.12 o superior. Detectado: $version"
}
Ok $version

Step "Preparando el entorno virtual"
if (Test-Path -LiteralPath $venvPython) {
    Ok "Ya existe .venv; se reutiliza."
} else {
    & $Python -m venv $venv
    if (-not (Test-Path -LiteralPath $venvPython)) { throw "No se pudo crear $venv." }
    Ok "Creado en $venv"
}

Step "Instalando dependencias"
& $venvPython -m pip install --quiet --upgrade pip
$requirements = if ($IncludeDevDependencies) { "requirements-dev.txt" } else { "requirements.txt" }
& $venvPython -m pip install --quiet -r (Join-Path $backend $requirements)
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de $requirements." }
Ok "Instalado $requirements"

Step "Configurando SQLite"
if (Test-Path -LiteralPath $envFile) {
    Ok "Ya existe .env; se conserva."
} else {
    Copy-Item (Join-Path $repositoryRoot ".env.example") $envFile
    $secret = & $venvPython -c "import secrets; print(secrets.token_urlsafe(50))"
    (Get-Content -LiteralPath $envFile -Raw -Encoding UTF8).Replace(
        "change-this-only-for-the-prototype", $secret
    ) | Set-Content -LiteralPath $envFile -Encoding UTF8 -NoNewline
    Ok "Creado .env con una clave propia."
}

Step "Aplicando migraciones"
Push-Location $backend
try {
    & $venvPython manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw "Falló la migración." }
    Step "Cargando Álgebra Octavo B"
    & $venvPython manage.py seed_exam
    if ($LASTEXITCODE -ne 0) { throw "Falló la carga del curso demo." }
}
finally { Pop-Location }

Write-Host ""
Write-Host "Backend instalado. Inícialo con:" -ForegroundColor Green
Write-Host "   .\scripts\windows\Start-Backend.ps1" -ForegroundColor Green
