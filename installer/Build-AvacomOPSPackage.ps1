<#
.SYNOPSIS
    Prepara la carga que empaqueta el instalador wizard de AVACOM OPS Core.

.DESCRIPTION
    Corre en la máquina de desarrollo, NO en el equipo del profesor. Deja en
    `installer\payload` todo lo que el profesor necesita, ya compilado:

      app\        panel del profesor, .exe autocontenido (sin runtime de .NET)
      backend\    la API de Django
      runtime\    Python 3.12.10 embebido con las dependencias ya instaladas
      service\    AVACOMOPSBackend, el servicio que mantiene la API en marcha

    La diferencia con el asistente anterior es que allí el equipo del profesor
    compilaba: descargaba el SDK de .NET, la carga MAUI y Python con winget, y
    tardaba media hora. Aquí eso ocurre una sola vez, aquí, y el profesor recibe
    un Setup.exe que sólo copia archivos.

    Python embebido y no un entorno virtual: un venv guarda la ruta absoluta de
    su intérprete base en pyvenv.cfg, así que deja de funcionar en cuanto se
    copia a otro equipo. La distribución embebida es autónoma y relocalizable,
    que es justo lo que exige un instalador.

.EXAMPLE
    .\installer\Build-AvacomOPSPackage.ps1
    .\installer\Build-AvacomOPSPackage.ps1 -SkipPublish   # reutiliza app\ ya compilada
#>
[CmdletBinding()]
param(
    [string] $RepoRoot,
    [string] $PythonVersion = "3.12.10",
    [string] $BuildPython = "",
    [switch] $SkipPublish,
    [switch] $SkipRuntime
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"   # las barras de Invoke-WebRequest ralentizan mucho

# La carpeta del script se resuelve en el cuerpo y no en el valor por defecto de
# un parámetro: según cómo se invoque el script (-File, -Command, dot-sourcing),
# $PSScriptRoot puede estar vacío durante la evaluación del bloque param, y el
# fallo resultante -"no se puede enlazar el argumento porque es una cadena
# vacía"- no dice nada sobre la causa real.
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $RepoRoot)  { $RepoRoot  = Split-Path -Parent $scriptDir }

$payload       = Join-Path $scriptDir "payload"
$appDir        = Join-Path $payload "app"
$backendDir    = Join-Path $payload "backend"
$runtimeDir    = Join-Path $payload "runtime"
$serviceDir    = Join-Path $payload "service"
$serviceProject = Join-Path $RepoRoot "src\Avacom.OPS.Backend.Service\Avacom.OPS.Backend.Service.csproj"
$masterProject = Join-Path $RepoRoot "src\Avacom.OPS.Master\Avacom.OPS.Master.csproj"
$backendSource = Join-Path $RepoRoot "backend"
$workDir       = Join-Path $env:TEMP "avacom-package-work"

function Write-Step([string] $text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

function Assert-Native([string] $description) {
    if ($LASTEXITCODE -ne 0) { throw "$description (código $LASTEXITCODE)" }
}

<#
 Localiza un Python con pip cuya versión coincida exactamente con la del runtime
 embebido. La coincidencia no es opcional: pip resuelve ruedas binarias por
 versión y arquitectura, así que instalar con 3.13 en un runtime 3.12 produce un
 paquete que importa mal en el equipo del profesor, no aquí.
#>
function Find-BuildPython([string] $version, [string] $preferred = "") {
    $candidates = @()
    if ($preferred) { $candidates += $preferred }
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $short = ($version -split '\.')[0..1] -join '.'
        $resolved = & py "-$short" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) { $candidates += $resolved.Trim() }
    }
    $onPath = Get-Command "python" -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    $candidates += @(
        "$env:ProgramFiles\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )

    foreach ($exe in $candidates | Where-Object { $_ -and (Test-Path $_) }) {
        $raw = (& $exe --version 2>&1 | Out-String).Trim()
        if ($raw -match "Python (\d+\.\d+)\.") {
            $found = $Matches[1]
            $wanted = ($version -split '\.')[0..1] -join '.'
            if ($found -eq $wanted) {
                & $exe -m pip --version *> $null
                if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Path = $exe } }
            }
        }
    }
    throw "No se encontró un Python $version con pip en esta máquina. Es necesario para preparar el runtime embebido."
}

<#
 Escribe el archivo ._pth que define sys.path del runtime embebido.

 Es la pieza mas delicada del paquete. En una distribucion embebida, la
 presencia de ._pth hace que sys.path sea EXACTAMENTE lo que ese archivo diga:
 se ignora PYTHONPATH y -esto es lo que rompe- tampoco se agrega el directorio
 del script que se ejecuta. Por eso `python backend\manage.py` fallaba con
 "No module named 'exam_master'" aunque el modulo estuviera junto a manage.py.

 Se declara entonces ..\backend de forma explicita. La ruta es relativa a la
 carpeta del ._pth, y la disposicion del paquete la fija este script: runtime\
 y backend\ son hermanas, tanto aqui como tras la instalacion.

 Idempotente: reescribe el archivo completo, asi que puede ejecutarse sobre un
 runtime ya preparado.
#>
function Set-RuntimePath([string] $runtime) {
    $pth = Get-ChildItem -Path $runtime -Filter "python*._pth" | Select-Object -First 1
    if (-not $pth) { throw "El runtime en $runtime no tiene python*._pth; no se puede definir sys.path." }

    $zip = Get-ChildItem -Path $runtime -Filter "python*.zip" | Select-Object -First 1
    $lines = @(
        "# Generado por Build-AvacomOPSPackage.ps1. sys.path del runtime embebido.",
        $(if ($zip) { $zip.Name } else { "python312.zip" }),
        ".",
        "Lib\site-packages",
        "# La API vive en la carpeta hermana. Sin esta linea, manage.py no",
        "# encuentra exam_master: el ._pth suprime el directorio del script.",
        "..\backend",
        "import site"
    )
    Set-Content -LiteralPath $pth.FullName -Value $lines -Encoding ASCII
    Write-Host "sys.path definido en $($pth.Name) (incluye ..\backend)"
}

if (-not (Test-Path $masterProject)) { throw "No se encuentra el proyecto del panel: $masterProject" }
if (-not (Test-Path (Join-Path $backendSource "manage.py"))) { throw "No se encuentra la API en $backendSource" }

New-Item -ItemType Directory -Force -Path $payload, $workDir | Out-Null

# ── 1. Panel del profesor ────────────────────────────────────────────────────
Write-Step "Panel del profesor (.exe autocontenido)"
if ($SkipPublish -and (Test-Path (Join-Path $appDir "Avacom.OPS.Master.exe"))) {
    Write-Host "Se reutiliza la compilación existente en app\"
}
else {
    Remove-Item -Recurse -Force $appDir -ErrorAction SilentlyContinue
    # self-contained + WindowsAppSDKSelfContained: el .exe corre en un equipo sin
    # runtime de .NET y sin el Windows App SDK instalado, que es el caso de la sede.
    & dotnet publish $masterProject `
        -f net9.0-windows10.0.19041.0 -c Release -r win-x64 `
        --self-contained -p:WindowsPackageType=None -p:WindowsAppSDKSelfContained=true `
        -o $appDir --nologo -v q
    Assert-Native "Falló la publicación del panel"
    if (-not (Test-Path (Join-Path $appDir "Avacom.OPS.Master.exe"))) {
        throw "La publicación terminó pero no apareció Avacom.OPS.Master.exe"
    }
}

# ── 2. API ───────────────────────────────────────────────────────────────────
Write-Step "API de Django"
# /MIR replica y limpia restos de una carga anterior. Se excluye lo que es del
# equipo y no del paquete: cachés, logs, la base local y el .env de desarrollo
# (el instalador genera uno propio con una clave nueva).
& robocopy $backendSource $backendDir /MIR /NFL /NDL /NJH /NJS `
    /XD __pycache__ logs .pytest_cache /XF db.sqlite3 *.pyc .env | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy no pudo copiar la API (código $LASTEXITCODE)" }
Write-Host "API copiada a backend\"

# ── 3. Python embebido con dependencias ──────────────────────────────────────
Write-Step "Python $PythonVersion embebido con dependencias"
if ($SkipRuntime -and (Test-Path (Join-Path $runtimeDir "python.exe"))) {
    Write-Host "Se reutiliza el runtime existente en runtime\"
}
else {
    Remove-Item -Recurse -Force $runtimeDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

    $zipName = "python-$PythonVersion-embed-amd64.zip"
    $zipPath = Join-Path $workDir $zipName
    if (-not (Test-Path $zipPath)) {
        Write-Host "Descargando $zipName…"
        Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$PythonVersion/$zipName" -OutFile $zipPath
    }
    else { Write-Host "Usando la descarga en caché: $zipPath" }

    Expand-Archive -LiteralPath $zipPath -DestinationPath $runtimeDir -Force

    $runtimePython = Join-Path $runtimeDir "python.exe"
    $sitePackages  = Join-Path $runtimeDir "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null

    # Las dependencias se instalan con el pip del Python del sistema apuntando al
    # runtime, en lugar de arrancar pip dentro del embebido con get-pip.py. Evita
    # una descarga más (que ya falló una vez en esta red), no envía pip en el
    # paquete y es reproducible. Requiere que las dos versiones coincidan, porque
    # las ruedas binarias son específicas de la versión y la arquitectura.
    $builder = Find-BuildPython $PythonVersion $BuildPython
    Write-Host "Instalando requirements.txt en el runtime con $($builder.Path)…"

    # $ErrorActionPreference se relaja SOLO alrededor de pip, y no por descuido.
    # Windows PowerShell 5.1 envuelve cada línea que un ejecutable nativo manda
    # a stderr en un ErrorRecord; con la preferencia en Stop, el aviso
    # "A new release of pip is available" aborta la compilación aunque pip haya
    # terminado en 0. Lo que decide si el paso funcionó es $LASTEXITCODE, y eso
    # es lo que comprueba Assert-Native.
    $preferenciaPrevia = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $builder.Path -m pip install -r (Join-Path $backendDir "requirements.txt") `
            --target $sitePackages --upgrade --no-warn-script-location --quiet
    }
    finally { $ErrorActionPreference = $preferenciaPrevia }
    Assert-Native "Falló la instalación de dependencias en el runtime"

    # __pycache__ no viaja: son megas que el instalador no necesita y que se
    # regeneran en el equipo del profesor la primera vez que corre la API.
    Get-ChildItem -Path $runtimeDir -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# sys.path se define siempre, incluso con -SkipRuntime: es la parte que más
# cambia y dejarla dentro del bloque que se puede saltar significaba reutilizar
# un ._pth obsoleto sin que nada lo indicara.
Set-RuntimePath $runtimeDir

# ── 3c. Servicio de Windows del backend ──────────────────────────────────────
Write-Step "Servicio AVACOMOPSBackend"
if ($SkipPublish -and (Test-Path (Join-Path $serviceDir "Avacom.OPS.Backend.Service.exe"))) {
    Write-Host "Se reutiliza el servicio existente en service\"
}
else {
    Remove-Item -Recurse -Force $serviceDir -ErrorAction SilentlyContinue
    # Autocontenido igual que el panel: el equipo del aula no tiene por qué
    # tener el runtime de .NET, y un servicio que no arranca por eso deja el
    # aula sin API sin decir por qué.
    & dotnet publish $serviceProject -c Release -r win-x64 `
        --self-contained -p:PublishSingleFile=true `
        -o $serviceDir --nologo -v q
    Assert-Native "Falló la publicación del servicio del backend"
    if (-not (Test-Path (Join-Path $serviceDir "Avacom.OPS.Backend.Service.exe"))) {
        throw "La publicación terminó pero no apareció Avacom.OPS.Backend.Service.exe"
    }
}

# ── 3b. El runtime funciona de verdad ────────────────────────────────────────
# Un pip que termina en 0 no garantiza nada: lo que decide si el paquete sirve es
# que el intérprete relocalizable importe las dependencias Y el proyecto. La
# segunda comprobación es la que faltaba y dejó pasar un ._pth sin ..\backend,
# con el que `manage.py migrate` fallaba ya instalado en el equipo de destino.
$runtimePython = Join-Path $runtimeDir "python.exe"

& $runtimePython -c "import django, daphne, channels, dotenv, rest_framework; print('dependencias OK')"
Assert-Native "El runtime embebido no puede importar las dependencias de la API"

# Se ejecuta desde una carpeta ajena a propósito: si sólo funcionara con el
# directorio de trabajo correcto, el ._pth seguiría estando mal.
Push-Location $env:TEMP
try {
    & $runtimePython -c "import exam_master.settings, exams; print('proyecto OK')"
    Assert-Native "El runtime no encuentra el proyecto (revisa ..\backend en el ._pth)"
}
finally { Pop-Location }

# ── 4. Resumen ───────────────────────────────────────────────────────────────
Write-Step "Carga preparada"
foreach ($part in @(@{N="app";      P=$appDir},
                    @{N="backend";  P=$backendDir},
                    @{N="runtime";  P=$runtimeDir},
                    @{N="service";  P=$serviceDir})) {
    $size = (Get-ChildItem -Path $part.P -Recurse -File -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    Write-Host ("  {0,-10} {1,8:N1} MB" -f $part.N, ($size / 1MB))
}
$total = (Get-ChildItem -Path $payload -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("  {0,-10} {1,8:N1} MB" -f "TOTAL", ($total / 1MB))
Write-Host ""
Write-Host "Siguiente paso: compilar el wizard con Build-Installer.ps1" -ForegroundColor Green
