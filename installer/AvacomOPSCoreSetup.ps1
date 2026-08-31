<#
.SYNOPSIS
    Asistente de instalación de AVACOM OPS Core (panel del profesor + API).

.DESCRIPTION
    Wizard clásico de Windows en cuatro pasos: Bienvenida → Verificación →
    Instalación → Finalizar. Lo lanza Install-AvacomOPSCore.bat ya elevado
    y en modo STA (WinForms no funciona sin STA).

    Qué instala, en orden:
      1. Python 3.12.10 (winget) si el equipo no lo tiene.
      2. La API Django copiada a la carpeta de destino, con un .env en SQLite:
         el equipo del profesor no debe necesitar Docker ni MongoDB.
      3. El entorno virtual prtvenv01-avacom con requirements.txt.
      4. La base de datos migrada y el curso demo sembrado.
      5. Las herramientas del .exe (.NET SDK 9 + carga MAUI) y la publicación
         del panel del profesor como ejecutable autocontenido.
      6. Start-AvacomOPSCore.bat: arranca la API, espera /health/ y abre el
         panel; al cerrar el panel apaga la API. Es el acceso del escritorio.
#>
[CmdletBinding()]
param(
    # Raíz del repositorio. Si se omite, se deduce en el cuerpo del script.
    [string] $RepoRoot
)

$ErrorActionPreference = "Stop"

# Se resuelve aquí y no en el valor por defecto del parámetro: según cómo se
# invoque el script, $PSScriptRoot puede estar vacío mientras se evalúa el bloque
# param, y entonces Split-Path aborta con "cadena vacía" antes de mostrar nada.
if (-not $RepoRoot) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $RepoRoot = Split-Path -Parent $scriptDir
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# ─────────────────────────────────────────────────────────────────────────────
#  Constantes de la instalación
# ─────────────────────────────────────────────────────────────────────────────
$Script:ProductName    = "AVACOM OPS Core"
$Script:RequiredPython = [Version]"3.12.10"
$Script:VenvName       = "prtvenv01-avacom"
$Script:ApiPort        = 8000
$Script:DefaultTarget  = "C:\AVACOM\Courses"
$Script:MasterProject  = Join-Path $RepoRoot "src\Avacom.OPS.Master\Avacom.OPS.Master.csproj"
$Script:BackendSource  = Join-Path $RepoRoot "backend"

# ─────────────────────────────────────────────────────────────────────────────
#  Detección de herramientas
# ─────────────────────────────────────────────────────────────────────────────

function Get-CommandPath([string] $name) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    return $null
}

<#
 Localiza un Python 3.12 utilizable. Se intenta primero el lanzador `py`,
 después el `python` del PATH y por último las rutas de instalación típicas,
 porque winget instala el intérprete pero la sesión actual no siempre ve el
 PATH actualizado sin reiniciar el proceso.
#>
function Find-Python312 {
    $candidates = @()
    if (Get-CommandPath "py") {
        $resolved = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) { $candidates += $resolved.Trim() }
    }
    $onPath = Get-CommandPath "python"
    if ($onPath) { $candidates += $onPath }
    $candidates += @(
        "$env:ProgramFiles\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )

    foreach ($exe in $candidates | Where-Object { $_ -and (Test-Path $_) }) {
        $raw = (& $exe --version 2>&1 | Out-String).Trim()   # "Python 3.12.10"
        if ($raw -match "Python (\d+\.\d+\.\d+)") {
            $version = [Version]$Matches[1]
            if ($version.Major -eq 3 -and $version.Minor -eq 12) {
                return [pscustomobject]@{ Path = $exe; Version = $version; Exact = ($version -eq $Script:RequiredPython) }
            }
        }
    }
    return $null
}

function Test-DotnetSdk9 {
    if (-not (Get-CommandPath "dotnet")) { return $false }
    $sdks = (& dotnet --list-sdks 2>$null | Out-String)
    return $sdks -match "(?m)^9\."
}

function Test-MauiWorkload {
    if (-not (Get-CommandPath "dotnet")) { return $false }
    $workloads = (& dotnet workload list 2>$null | Out-String)
    return $workloads -match "maui"
}

function Test-PortFree([int] $port) {
    $inUse = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return -not $inUse
}

# ─────────────────────────────────────────────────────────────────────────────
#  Interfaz: formulario y navegación
# ─────────────────────────────────────────────────────────────────────────────

$form                 = New-Object System.Windows.Forms.Form
$form.Text            = "$Script:ProductName — Instalación"
$form.ClientSize      = New-Object System.Drawing.Size(640, 460)
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox     = $false
$form.StartPosition   = "CenterScreen"
$form.Font            = New-Object System.Drawing.Font("Segoe UI", 9.5)

# Franja lateral: el rasgo visual clásico de un instalador de Windows.
$side           = New-Object System.Windows.Forms.Panel
$side.Size      = New-Object System.Drawing.Size(170, 400)
$side.Location  = New-Object System.Drawing.Point(0, 0)
$side.BackColor = [System.Drawing.Color]::FromArgb(27, 52, 69)   # Ink de la app
$form.Controls.Add($side)

$sideTitle           = New-Object System.Windows.Forms.Label
$sideTitle.Text      = "AVACOM`nOPS Core"
$sideTitle.ForeColor = [System.Drawing.Color]::White
$sideTitle.Font      = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
$sideTitle.Location  = New-Object System.Drawing.Point(18, 24)
$sideTitle.Size      = New-Object System.Drawing.Size(140, 70)
$side.Controls.Add($sideTitle)

$sideSteps           = New-Object System.Windows.Forms.Label
$sideSteps.ForeColor = [System.Drawing.Color]::FromArgb(190, 210, 220)
$sideSteps.Font      = New-Object System.Drawing.Font("Segoe UI", 9)
$sideSteps.Location  = New-Object System.Drawing.Point(18, 110)
$sideSteps.Size      = New-Object System.Drawing.Size(145, 200)
$side.Controls.Add($sideSteps)

# Zona de contenido: un panel por página, se muestra una a la vez.
$content          = New-Object System.Windows.Forms.Panel
$content.Location = New-Object System.Drawing.Point(170, 0)
$content.Size     = New-Object System.Drawing.Size(470, 400)
$form.Controls.Add($content)

# Barra inferior de botones.
$buttonBar           = New-Object System.Windows.Forms.Panel
$buttonBar.Location  = New-Object System.Drawing.Point(0, 400)
$buttonBar.Size      = New-Object System.Drawing.Size(640, 60)
$buttonBar.BackColor = [System.Drawing.Color]::FromArgb(240, 243, 245)
$form.Controls.Add($buttonBar)

function New-NavButton([string] $text, [int] $x) {
    $button          = New-Object System.Windows.Forms.Button
    $button.Text     = $text
    $button.Size     = New-Object System.Drawing.Size(100, 30)
    $button.Location = New-Object System.Drawing.Point($x, 15)
    $buttonBar.Controls.Add($button)
    return $button
}
$backButton   = New-NavButton "< Atrás"    405
$nextButton   = New-NavButton "Siguiente >" 510
$cancelButton = New-NavButton "Cancelar"    290

function New-Page {
    $page         = New-Object System.Windows.Forms.Panel
    $page.Size    = $content.Size
    $page.Visible = $false
    $content.Controls.Add($page)
    return $page
}

function New-PageTitle($page, [string] $text) {
    $label          = New-Object System.Windows.Forms.Label
    $label.Text     = $text
    $label.Font     = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
    $label.Location = New-Object System.Drawing.Point(24, 20)
    $label.Size     = New-Object System.Drawing.Size(420, 30)
    $page.Controls.Add($label)
}

# ── Página 1 · Bienvenida ────────────────────────────────────────────────────
$welcomePage = New-Page
New-PageTitle $welcomePage "Bienvenido"

$welcomeText          = New-Object System.Windows.Forms.Label
$welcomeText.Location = New-Object System.Drawing.Point(24, 60)
$welcomeText.Size     = New-Object System.Drawing.Size(420, 190)
$welcomeText.Text     = @"
Este asistente instala el panel del profesor de $Script:ProductName y la API que lo acompaña en este equipo.

Qué va a hacer:

  •  Verificar Python 3.12.10 e instalarlo con winget si falta
  •  Crear el entorno virtual $Script:VenvName
  •  Instalar las dependencias de requirements.txt
  •  Preparar lo necesario y compilar el .exe del panel
  •  Dejar un acceso que arranca la API automáticamente

Cierra el panel del profesor si está abierto y pulsa Siguiente.
"@
$welcomePage.Controls.Add($welcomeText)

$targetLabel          = New-Object System.Windows.Forms.Label
$targetLabel.Text     = "Carpeta de instalación:"
$targetLabel.Location = New-Object System.Drawing.Point(24, 285)
$targetLabel.Size     = New-Object System.Drawing.Size(420, 20)
$welcomePage.Controls.Add($targetLabel)

$targetBox          = New-Object System.Windows.Forms.TextBox
$targetBox.Text     = $Script:DefaultTarget
$targetBox.Location = New-Object System.Drawing.Point(24, 310)
$targetBox.Size     = New-Object System.Drawing.Size(330, 24)
$welcomePage.Controls.Add($targetBox)

$browseButton          = New-Object System.Windows.Forms.Button
$browseButton.Text     = "Examinar…"
$browseButton.Location = New-Object System.Drawing.Point(362, 308)
$browseButton.Size     = New-Object System.Drawing.Size(84, 26)
$browseButton.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Elige la carpeta de instalación"
    if ($dialog.ShowDialog($form) -eq "OK") { $targetBox.Text = Join-Path $dialog.SelectedPath "AVACOM-Courses" }
})
$welcomePage.Controls.Add($browseButton)

# ── Página 2 · Verificación del equipo ───────────────────────────────────────
$checksPage = New-Page
New-PageTitle $checksPage "Verificación del equipo"

$checksInfo          = New-Object System.Windows.Forms.Label
$checksInfo.Text     = "Lo marcado con  ✗  bloquea la instalación. Lo marcado con  !  se resuelve durante la instalación."
$checksInfo.Location = New-Object System.Drawing.Point(24, 55)
$checksInfo.Size     = New-Object System.Drawing.Size(420, 35)
$checksPage.Controls.Add($checksInfo)

$checksList               = New-Object System.Windows.Forms.ListView
$checksList.View          = "Details"
$checksList.FullRowSelect = $true
$checksList.HeaderStyle   = "Nonclickable"
$checksList.Location      = New-Object System.Drawing.Point(24, 95)
$checksList.Size          = New-Object System.Drawing.Size(422, 265)
[void]$checksList.Columns.Add("", 34)
[void]$checksList.Columns.Add("Comprobación", 170)
[void]$checksList.Columns.Add("Detalle", 210)
$checksPage.Controls.Add($checksList)

function Add-CheckRow([string] $state, [string] $name, [string] $detail) {
    $row = New-Object System.Windows.Forms.ListViewItem($state)
    [void]$row.SubItems.Add($name)
    [void]$row.SubItems.Add($detail)
    $row.ForeColor = switch ($state) {
        "✓"     { [System.Drawing.Color]::FromArgb(60, 140, 114) }
        "!"     { [System.Drawing.Color]::FromArgb(160, 110, 20) }
        default { [System.Drawing.Color]::FromArgb(184, 93, 103) }
    }
    [void]$checksList.Items.Add($row)
}

<#
 Ejecuta todas las comprobaciones y decide si se puede continuar. Devuelve
 $true si no hay ningún bloqueo. Los faltantes que el propio instalador sabe
 resolver (Python, SDK, workload) se marcan con "!" y no bloquean.
#>
function Invoke-Checks {
    $checksList.Items.Clear()
    $blocked = $false

    $os = [System.Environment]::OSVersion.Version
    if ($os.Major -ge 10) { Add-CheckRow "✓" "Windows" "versión $($os.Major).$($os.Build)" }
    else { Add-CheckRow "✗" "Windows" "se requiere Windows 10 u 11"; $blocked = $true }

    $winget = [bool](Get-CommandPath "winget")
    if ($winget) { Add-CheckRow "✓" "winget" "disponible" }
    else { Add-CheckRow "!" "winget" "no disponible: sólo bloquea si falta Python" }

    $python = Find-Python312
    if ($python -and $python.Exact) { Add-CheckRow "✓" "Python 3.12.10" $python.Path }
    elseif ($python) { Add-CheckRow "!" "Python 3.12.10" "hay $($python.Version); se usará esa versión" }
    elseif ($winget) { Add-CheckRow "!" "Python 3.12.10" "falta: se instalará con winget" }
    else { Add-CheckRow "✗" "Python 3.12.10" "falta y no hay winget para instalarlo"; $blocked = $true }

    if (Test-DotnetSdk9) { Add-CheckRow "✓" ".NET SDK 9" "instalado" }
    elseif ($winget) { Add-CheckRow "!" ".NET SDK 9" "falta: se instalará con winget" }
    else { Add-CheckRow "✗" ".NET SDK 9" "falta y no hay winget para instalarlo"; $blocked = $true }

    if (Test-MauiWorkload) { Add-CheckRow "✓" "Carga MAUI" "instalada" }
    else { Add-CheckRow "!" "Carga MAUI" "falta: se instalará (descarga grande)" }

    if ((Test-Path $Script:MasterProject) -and (Test-Path (Join-Path $Script:BackendSource "manage.py"))) {
        Add-CheckRow "✓" "Código fuente" $RepoRoot
    }
    else { Add-CheckRow "✗" "Código fuente" "ejecuta el instalador desde la carpeta del repositorio"; $blocked = $true }

    if (Test-PortFree $Script:ApiPort) { Add-CheckRow "✓" "Puerto $Script:ApiPort" "libre" }
    else { Add-CheckRow "!" "Puerto $Script:ApiPort" "en uso: cierra la API anterior antes de arrancar" }

    return -not $blocked
}

# ── Página 3 · Instalación ───────────────────────────────────────────────────
$installPage = New-Page
New-PageTitle $installPage "Instalando"

$stepLabel          = New-Object System.Windows.Forms.Label
$stepLabel.Location = New-Object System.Drawing.Point(24, 58)
$stepLabel.Size     = New-Object System.Drawing.Size(420, 22)
$stepLabel.Text     = "Preparado para instalar. Pulsa Instalar."
$installPage.Controls.Add($stepLabel)

$progressBar          = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(24, 84)
$progressBar.Size     = New-Object System.Drawing.Size(422, 18)
$installPage.Controls.Add($progressBar)

$logBox            = New-Object System.Windows.Forms.TextBox
$logBox.Multiline  = $true
$logBox.ReadOnly   = $true
$logBox.ScrollBars = "Vertical"
$logBox.Font       = New-Object System.Drawing.Font("Consolas", 8.5)
$logBox.Location   = New-Object System.Drawing.Point(24, 112)
$logBox.Size       = New-Object System.Drawing.Size(422, 248)
$installPage.Controls.Add($logBox)

function Write-Log([string] $line) {
    $logBox.AppendText($line + [Environment]::NewLine)
    [System.Windows.Forms.Application]::DoEvents()
}

<#
 Ejecuta un programa externo volcando su salida al cuadro de registro.

 La salida se redirige a archivos y se lee por sondeo, en lugar de leer los
 streams del proceso directamente: ReadLine() bloquea el único hilo que tiene
 este script, que es también el de la interfaz, y el asistente se congelaría
 con "(No responde)" durante pasos largos como la carga de trabajo de MAUI.
#>
function Invoke-Logged([string] $exe, [string[]] $arguments) {
    $stamp   = [Guid]::NewGuid().ToString("N")
    $outFile = Join-Path $env:TEMP "avacom-install-$stamp.out"
    $errFile = Join-Path $env:TEMP "avacom-install-$stamp.err"

    Write-Log ("> " + $exe + " " + ($arguments -join " "))
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -NoNewWindow -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    # Sin capturar el handle, .ExitCode devuelve $null en procesos que ya terminaron
    # (comportamiento documentado de -PassThru en Windows PowerShell). Con $null,
    # Assert-Logged abortaría pasos que en realidad terminaron bien.
    $null = $process.Handle

    $readSoFar = 0
    while (-not $process.HasExited) {
        Start-Sleep -Milliseconds 250
        [System.Windows.Forms.Application]::DoEvents()
        if (Test-Path $outFile) {
            $lines = @(Get-Content $outFile -ErrorAction SilentlyContinue)
            for ($i = $readSoFar; $i -lt $lines.Count; $i++) { Write-Log ("  " + $lines[$i]) }
            $readSoFar = $lines.Count
        }
    }

    # Cola final de salida y todo stderr (winget y pip escriben avisos ahí).
    $lines = @(Get-Content $outFile -ErrorAction SilentlyContinue)
    for ($i = $readSoFar; $i -lt $lines.Count; $i++) { Write-Log ("  " + $lines[$i]) }
    foreach ($line in @(Get-Content $errFile -ErrorAction SilentlyContinue)) { Write-Log ("  ! " + $line) }
    Remove-Item $outFile, $errFile -ErrorAction SilentlyContinue

    return $process.ExitCode
}

function Assert-Logged([string] $exe, [string[]] $arguments, [string] $failureMessage) {
    $code = Invoke-Logged $exe $arguments
    if ($code -ne 0) { throw "$failureMessage (código $code)" }
}

# ─────────────────────────────────────────────────────────────────────────────
#  Pasos de instalación
# ─────────────────────────────────────────────────────────────────────────────

function Install-PythonStep([string] $target) {
    $python = Find-Python312
    if ($python) {
        if ($python.Exact) { Write-Log "Python 3.12.10 exacto ya instalado: $($python.Path)" }
        else { Write-Log "AVISO: hay Python $($python.Version) (se pedía 3.12.10 exacto). Se usará esa versión." }
        return $python
    }
    Write-Log "Python 3.12 no encontrado: instalando 3.12.10 con winget…"
    Assert-Logged "winget" @("install", "-e", "--id", "Python.Python.3.12", "--version", "3.12.10",
        "--scope", "machine", "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity") "No se pudo instalar Python con winget"
    $python = Find-Python312
    if (-not $python) { throw "winget terminó pero Python 3.12 sigue sin aparecer. Reinicia el instalador." }
    return $python
}

function Copy-BackendStep([string] $target) {
    Write-Log "Copiando la API a $target\backend…"
    # /MIR replica y limpia restos de instalaciones previas; se excluye lo que no
    # es código: cachés, logs y la base local (que es del equipo, no del paquete).
    $code = Invoke-Logged "robocopy" @($Script:BackendSource, (Join-Path $target "backend"),
        "/MIR", "/NFL", "/NDL", "/NJH", "/NJS",
        "/XD", "__pycache__", "logs", ".pytest_cache",
        "/XF", "db.sqlite3", "*.pyc", ".env")
    # robocopy usa códigos 0-7 como éxito; 8+ es error de verdad.
    if ($code -ge 8) { throw "robocopy no pudo copiar la API (código $code)" }

    $envFile = Join-Path $target ".env"
    if (Test-Path $envFile) {
        Write-Log ".env existente conservado (configuración de la sede)."
        return
    }
    # SQLite a propósito: el equipo del profesor no debe requerir MongoDB ni
    # Docker. La clave se genera por instalación para no compartir una fija.
    $secret = -join ((48..57) + (97..122) | Get-Random -Count 50 | ForEach-Object { [char]$_ })
    @(
        "# Generado por el instalador de $Script:ProductName",
        "DJANGO_SECRET_KEY=$secret",
        "DJANGO_DEBUG=0",
        "DJANGO_ALLOWED_HOSTS=*",
        "DJANGO_LOG_LEVEL=INFO",
        "DB_ENGINE=sqlite",
        "API_PORT=$Script:ApiPort"
    ) | Set-Content -LiteralPath $envFile -Encoding ASCII
    Write-Log ".env creado con SQLite (sin dependencia de MongoDB)."
}

function New-VenvStep([string] $target, $python) {
    $venvPath   = Join-Path $target $Script:VenvName
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Log "Entorno virtual ya existente: $venvPath"
        return $venvPython
    }
    Write-Log "Creando entorno virtual $Script:VenvName…"
    Assert-Logged $python.Path @("-m", "venv", $venvPath) "No se pudo crear el entorno virtual"
    return $venvPython
}

function Install-RequirementsStep([string] $target, [string] $venvPython) {
    $requirements = Join-Path $target "backend\requirements.txt"
    Write-Log "Actualizando pip…"
    Assert-Logged $venvPython @("-m", "pip", "install", "--upgrade", "pip", "--quiet") "No se pudo actualizar pip"
    Write-Log "Instalando requirements.txt…"
    Assert-Logged $venvPython @("-m", "pip", "install", "-r", $requirements) "Falló la instalación de dependencias"
}

function Initialize-DatabaseStep([string] $target, [string] $venvPython) {
    $manage = Join-Path $target "backend\manage.py"
    Write-Log "Aplicando migraciones…"
    Assert-Logged $venvPython @($manage, "migrate", "--noinput") "Fallaron las migraciones"
    Write-Log "Sembrando Álgebra Octavo B y el quiz de México…"
    Assert-Logged $venvPython @($manage, "seed_exam") "No se pudo sembrar el curso demo"
}

function Install-DotnetStep {
    if (-not (Test-DotnetSdk9)) {
        Write-Log "Instalando .NET SDK 9 con winget…"
        Assert-Logged "winget" @("install", "-e", "--id", "Microsoft.DotNet.SDK.9",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity") `
            "No se pudo instalar el SDK de .NET"
    } else { Write-Log ".NET SDK 9 ya instalado." }

    if (-not (Test-MauiWorkload)) {
        Write-Log "Instalando la carga de trabajo MAUI (esto puede tardar varios minutos)…"
        Assert-Logged "dotnet" @("workload", "install", "maui-windows") "No se pudo instalar la carga MAUI"
    } else { Write-Log "Carga MAUI ya instalada." }
}

function Publish-MasterStep([string] $target) {
    $output = Join-Path $target "app"
    Write-Log "Compilando el panel del profesor (.exe autocontenido)…"
    # Autocontenido y sin empaquetar: el .exe corre en un equipo sin runtime de
    # .NET y sin certificado de firma, que es el caso del PC de la sede.
    Assert-Logged "dotnet" @("publish", $Script:MasterProject,
        "-f", "net9.0-windows10.0.19041.0", "-c", "Release", "-r", "win-x64",
        "--self-contained", "-p:WindowsPackageType=None", "-p:WindowsAppSDKSelfContained=true",
        "-o", $output) "Falló la publicación del panel"
    if (-not (Test-Path (Join-Path $output "Avacom.OPS.Master.exe"))) {
        throw "La publicación terminó pero no aparece Avacom.OPS.Master.exe en $output"
    }
}

function Write-LauncherStep([string] $target) {
    $launcher = Join-Path $target "Start-AvacomOPSCore.bat"
    Write-Log "Escribiendo el arranque $launcher…"
    # El BAT arranca la API ANTES de abrir el panel y la apaga al cerrarlo. El
    # panel ya trae su indicador verde/rojo, así que si la API tardara en subir
    # el profesor lo ve en pantalla en lugar de en una consola.
    @"
@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AVACOM OPS Core
set "ROOT=%~dp0"
set "VENVPY=%ROOT%$Script:VenvName\Scripts\python.exe"

if not exist "%VENVPY%" (
    echo No existe el entorno virtual. Vuelve a ejecutar el instalador.
    pause
    exit /b 1
)

rem Migraciones por si esta version trae cambios de esquema; es idempotente.
"%VENVPY%" "%ROOT%backend\manage.py" migrate --noinput >nul 2>&1

rem API con daphne, el mismo servidor ASGI del despliegue. Se captura el PID
rem para apagar exactamente ese proceso al salir, no cualquier python abierto.
set "APIPID="
for /f %%p in ('powershell -NoProfile -Command "(Start-Process -FilePath '%VENVPY%' -ArgumentList '-m','daphne','-b','0.0.0.0','-p','$Script:ApiPort','exam_master.asgi:application' -WorkingDirectory '%ROOT%backend' -WindowStyle Minimized -PassThru).Id"') do set "APIPID=%%p"

if not defined APIPID (
    echo No fue posible iniciar la API.
    pause
    exit /b 1
)

rem Esperar a /health/ hasta 20 segundos; si no responde se abre el panel
rem igualmente: su indicador quedara en rojo y explica el estado.
powershell -NoProfile -Command "for(`$i=0;`$i -lt 40;`$i++){ try{ if((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:$Script:ApiPort/health/ -TimeoutSec 2).StatusCode -eq 200){ exit 0 } }catch{}; Start-Sleep -Milliseconds 500 }; exit 1" >nul 2>&1

start /wait "" "%ROOT%app\Avacom.OPS.Master.exe"

rem Al cerrar el panel se apaga la API (/T incluye procesos hijos).
taskkill /pid %APIPID% /t /f >nul 2>&1
exit /b 0
"@ | Set-Content -LiteralPath $launcher -Encoding ASCII
}

# ─────────────────────────────────────────────────────────────────────────────
#  Motor de instalación
# ─────────────────────────────────────────────────────────────────────────────

$Script:InstallSucceeded = $false

function Start-Installation {
    $target = $targetBox.Text.Trim()
    $steps = @(
        @{ Name = "Python 3.12.10";               Action = { $Script:PythonInfo = Install-PythonStep $target } },
        @{ Name = "Copia de la API y .env";       Action = { Copy-BackendStep $target } },
        @{ Name = "Entorno virtual $Script:VenvName"; Action = { $Script:VenvPython = New-VenvStep $target $Script:PythonInfo } },
        @{ Name = "Dependencias de requirements.txt"; Action = { Install-RequirementsStep $target $Script:VenvPython } },
        @{ Name = "Base de datos y curso demo";   Action = { Initialize-DatabaseStep $target $Script:VenvPython } },
        @{ Name = "Herramientas del .exe";        Action = { Install-DotnetStep } },
        @{ Name = "Compilación del panel (.exe)"; Action = { Publish-MasterStep $target } },
        @{ Name = "Arranque automático de la API"; Action = { Write-LauncherStep $target } }
    )

    $progressBar.Maximum = $steps.Count
    $progressBar.Value   = 0
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    foreach ($step in $steps) {
        $stepLabel.Text = "Paso $($progressBar.Value + 1) de $($steps.Count): $($step.Name)"
        Write-Log ""
        Write-Log ("═══ " + $step.Name + " ═══")
        [System.Windows.Forms.Application]::DoEvents()
        & $step.Action
        $progressBar.Value += 1
    }

    $stepLabel.Text = "Instalación completada."
    Write-Log ""
    Write-Log "✓ Instalación completada en $target"
    $Script:InstallSucceeded = $true
}

# ── Página 4 · Finalizar ─────────────────────────────────────────────────────
$finishPage = New-Page
New-PageTitle $finishPage "Instalación completada"

$finishText          = New-Object System.Windows.Forms.Label
$finishText.Location = New-Object System.Drawing.Point(24, 60)
$finishText.Size     = New-Object System.Drawing.Size(420, 130)
$finishPage.Controls.Add($finishText)

$shortcutCheck          = New-Object System.Windows.Forms.CheckBox
$shortcutCheck.Text     = "Crear acceso directo en el escritorio"
$shortcutCheck.Checked  = $true
$shortcutCheck.Location = New-Object System.Drawing.Point(28, 210)
$shortcutCheck.Size     = New-Object System.Drawing.Size(400, 24)
$finishPage.Controls.Add($shortcutCheck)

$launchCheck          = New-Object System.Windows.Forms.CheckBox
$launchCheck.Text     = "Iniciar $Script:ProductName al terminar"
$launchCheck.Checked  = $true
$launchCheck.Location = New-Object System.Drawing.Point(28, 240)
$launchCheck.Size     = New-Object System.Drawing.Size(400, 24)
$finishPage.Controls.Add($launchCheck)

function Complete-Setup {
    $target   = $targetBox.Text.Trim()
    $launcher = Join-Path $target "Start-AvacomOPSCore.bat"

    if ($shortcutCheck.Checked) {
        # El acceso apunta al BAT (API + panel juntos), nunca al exe directo:
        # abrir sólo el exe dejaría el panel con el indicador en rojo.
        $shell    = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "AVACOM OPS Core.lnk"))
        $shortcut.TargetPath       = $launcher
        $shortcut.WorkingDirectory = $target
        $shortcut.IconLocation     = (Join-Path $target "app\Avacom.OPS.Master.exe") + ",0"
        $shortcut.Description      = "Inicia la API de AVACOM y abre el panel del profesor"
        $shortcut.Save()
    }
    if ($launchCheck.Checked) {
        Start-Process -FilePath $launcher -WorkingDirectory $target
    }
}

# ─────────────────────────────────────────────────────────────────────────────
#  Navegación entre páginas
# ─────────────────────────────────────────────────────────────────────────────

$pages = @($welcomePage, $checksPage, $installPage, $finishPage)
$pageNames = @("Bienvenida", "Verificación", "Instalación", "Finalizar")
$Script:PageIndex = 0

function Update-SideSteps {
    $lines = for ($i = 0; $i -lt $pageNames.Count; $i++) {
        if ($i -eq $Script:PageIndex) { "▸ " + $pageNames[$i] } else { "   " + $pageNames[$i] }
    }
    $sideSteps.Text = $lines -join "`n`n"
}

function Show-Page([int] $index) {
    $Script:PageIndex = $index
    for ($i = 0; $i -lt $pages.Count; $i++) { $pages[$i].Visible = ($i -eq $index) }
    Update-SideSteps

    $backButton.Enabled = ($index -eq 1)          # sólo tiene sentido volver de Verificación
    $cancelButton.Enabled = ($index -le 2)
    switch ($index) {
        0 { $nextButton.Text = "Siguiente >"; $nextButton.Enabled = $true }
        1 { $nextButton.Text = "Siguiente >"; $nextButton.Enabled = (Invoke-Checks) }
        2 { $nextButton.Text = "Instalar";    $nextButton.Enabled = $true }
        3 {
            $nextButton.Text = "Finalizar"; $nextButton.Enabled = $true
            $backButton.Enabled = $false
            $finishText.Text = "$Script:ProductName quedó instalado en:`n`n$($targetBox.Text)`n`nEl acceso Start-AvacomOPSCore.bat arranca la API de Python automáticamente y abre el panel del profesor. Al cerrar el panel, la API se apaga sola."
        }
    }
}

$backButton.Add_Click({ if ($Script:PageIndex -gt 0) { Show-Page ($Script:PageIndex - 1) } })

$nextButton.Add_Click({
    switch ($Script:PageIndex) {
        0 {
            if ([string]::IsNullOrWhiteSpace($targetBox.Text)) {
                [System.Windows.Forms.MessageBox]::Show("Indica la carpeta de instalación.", $Script:ProductName) | Out-Null
                return
            }
            Show-Page 1
        }
        1 { Show-Page 2 }
        2 {
            $nextButton.Enabled = $false
            $backButton.Enabled = $false
            $cancelButton.Enabled = $false
            try {
                Start-Installation
                Show-Page 3
            }
            catch {
                Write-Log ""
                Write-Log ("✗ ERROR: " + $_.Exception.Message)
                $stepLabel.Text = "La instalación se detuvo por un error."
                [System.Windows.Forms.MessageBox]::Show(
                    "La instalación se detuvo:`n`n$($_.Exception.Message)`n`nRevisa el registro, corrige la causa y pulsa Instalar para reintentar: los pasos ya completados se detectan y no se repiten.",
                    $Script:ProductName, "OK", "Error") | Out-Null
                $nextButton.Text = "Instalar"
                $nextButton.Enabled = $true
                $cancelButton.Enabled = $true
            }
        }
        3 {
            Complete-Setup
            $form.Close()
        }
    }
})

$cancelButton.Add_Click({
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "¿Salir del instalador?", $Script:ProductName, "YesNo", "Question")
    if ($answer -eq "Yes") { $form.Close() }
})

Show-Page 0
[void]$form.ShowDialog()

if ($Script:InstallSucceeded) { exit 0 } else { exit 1 }
