<#
.SYNOPSIS
    Produce dist\AvacomOPSMaster-Setup-<version>.exe.

.DESCRIPTION
    Un solo comando en la máquina de desarrollo. Hace dos cosas en orden:

      1. Prepara la carga  -> Build-AvacomOPSPackage.ps1
      2. Compila el wizard -> ISCC.exe AvacomOPSMaster.iss

    El resultado queda en dist\ en la raíz del repositorio: eso es lo que se
    entrega.

    Requiere Inno Setup 6 en la máquina de COMPILACIÓN. No en el equipo del
    aula: ahí solo llega el Setup.exe. Si no está, este script lo dice y ofrece
    el comando de winget en vez de instalarlo por su cuenta, porque instalar
    software en la máquina de alguien no es una decisión de un script de build.

.EXAMPLE
    .\installer\Build-Installer.ps1
    .\installer\Build-Installer.ps1 -SoloWizard        # reutiliza la carga ya preparada
    .\installer\Build-Installer.ps1 -InstalarInnoSetup # lo instala con winget y sigue
#>
[CmdletBinding()]
param(
    [string] $RepoRoot,
    [switch] $SoloWizard,
    [switch] $InstalarInnoSetup
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $RepoRoot)  { $RepoRoot  = Split-Path -Parent $scriptDir }

$iss  = Join-Path $scriptDir "AvacomOPSMaster.iss"
$dist = Join-Path $RepoRoot "dist"

function Write-Paso([string] $texto) {
    Write-Host ""
    Write-Host ("== " + $texto) -ForegroundColor Cyan
}

# ── Inno Setup ───────────────────────────────────────────────────────────────
function Find-Iscc {
    # Se buscan las tres rutas reales: la instalación por máquina de 64 y 32
    # bits, y la por usuario que hace winget.
    $candidatos = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles         "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA         "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($c in $candidatos) { if ($c -and (Test-Path $c)) { return $c } }
    $enRuta = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($enRuta) { return $enRuta.Source }
    return $null
}

Write-Paso "Inno Setup 6"
$iscc = Find-Iscc
if (-not $iscc -and $InstalarInnoSetup) {
    Write-Host "No esta instalado. Instalando con winget…"
    & winget install --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --silent
    $iscc = Find-Iscc
}
if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 no esta en esta maquina, y es lo que compila el wizard." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  winget install --id JRSoftware.InnoSetup" -ForegroundColor White
    Write-Host ""
    Write-Host "O vuelve a ejecutar este script con -InstalarInnoSetup para que lo haga." -ForegroundColor Yellow
    Write-Host "Solo hace falta AQUI: al equipo del aula llega unicamente el Setup.exe." -ForegroundColor Yellow
    throw "Falta Inno Setup 6 (ISCC.exe)."
}
Write-Host "ISCC: $iscc"

# ── 1 · la carga ─────────────────────────────────────────────────────────────
if ($SoloWizard) {
    Write-Paso "Carga (se reutiliza la existente)"
    foreach ($parte in @("app\Avacom.OPS.Master.exe", "backend\manage.py",
                         "runtime\python.exe", "service\Avacom.OPS.Backend.Service.exe")) {
        $ruta = Join-Path $scriptDir "payload\$parte"
        if (-not (Test-Path $ruta)) {
            throw "Falta $parte en la carga. Ejecuta sin -SoloWizard para prepararla."
        }
    }
    Write-Host "La carga esta completa."
}
else {
    Write-Paso "Preparando la carga"
    & (Join-Path $scriptDir "Build-AvacomOPSPackage.ps1") -RepoRoot $RepoRoot
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "La preparacion de la carga fallo." }
}

# ── 2 · el wizard ────────────────────────────────────────────────────────────
Write-Paso "Compilando el asistente"
New-Item -ItemType Directory -Path $dist -Force | Out-Null
& $iscc "/Q" $iss
if ($LASTEXITCODE -ne 0) { throw "ISCC devolvio $LASTEXITCODE" }

# ── 3 · resultado ────────────────────────────────────────────────────────────
Write-Paso "Listo"
$setups = Get-ChildItem -Path $dist -Filter "AvacomOPSMaster-Setup-*.exe" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending
if (-not $setups) { throw "ISCC termino en 0 pero no aparecio ningun Setup.exe en $dist" }

$setup = $setups[0]
Write-Host ("  {0}" -f $setup.FullName)
Write-Host ("  {0:N1} MB" -f ($setup.Length / 1MB))
Write-Host ""
Write-Host "Eso es lo que se entrega. En el equipo del aula solo hay que ejecutarlo." -ForegroundColor Green
