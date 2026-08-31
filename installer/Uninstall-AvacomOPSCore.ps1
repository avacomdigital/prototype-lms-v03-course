<#
.SYNOPSIS
    Desinstala AVACOM OPS Core para poder instalar una version nueva.

.DESCRIPTION
    Deja el equipo listo para ejecutar un Setup.exe mas reciente. Quita el panel,
    la API, el runtime embebido, el entorno virtual, los accesos directos, la
    regla de firewall y la entrada de "Agregar o quitar programas".

    Lo que NO toca, por diseno:

      * Python del sistema. El runtime que se borra es el embebido que vive
        dentro de la carpeta de instalacion, no el interprete que el equipo
        tenga instalado para otras cosas.
      * MongoDB. Ni el servicio de Windows, ni sus datos, ni el volumen
        mongo_data de Docker. Una instalacion hecha con el Setup.exe usa SQLite
        y nunca escribe en Mongo, pero la exclusion es explicita.
      * Cualquier otro producto. La instalacion se localiza por el AppId exacto
        del instalador, no por nombre: en este equipo convive un "AVACOM LMS"
        distinto (bajo C:\xampp) que una busqueda por nombre habria borrado.

    Los datos (.env y la base SQLite con los resultados) se respaldan antes de
    borrar. Perder los resultados de un examen ya rendido no se deshace, asi que
    el respaldo es el comportamiento por omision y hay que pedir -PurgeData para
    renunciar a el.

.PARAMETER Path
    Carpeta de instalacion. Solo hace falta si se instalo en una ruta no
    estandar; en caso normal se descubre sola.

.PARAMETER PurgeData
    No respalda: borra tambien .env y la base de datos. Uso previsto: preparar un
    equipo para otra sede.

.PARAMETER DryRun
    Muestra lo que haria sin borrar nada.

.EXAMPLE
    .\installer\Uninstall-AvacomOPSCore.ps1 -DryRun
    .\installer\Uninstall-AvacomOPSCore.ps1
    .\installer\Uninstall-AvacomOPSCore.ps1 -PurgeData -Force
#>
[CmdletBinding()]
param(
    [string] $Path,
    [switch] $PurgeData,
    [switch] $DryRun,
    [switch] $Force
)

$ErrorActionPreference = "Stop"

# ── Constantes que definen QUE se desinstala ────────────────────────────────
# El AppId es la unica forma segura de identificar el producto: coincide con
# [Setup] AppId de AvacomOPSCore.iss, e Inno le anade el sufijo _is1 en el
# registro. Buscar por DisplayName encontraria otros productos "AVACOM".
$AppId        = "{7D4C1E92-3A8B-4F51-9C6D-AE2B45F80C13}_is1"
$ProductName  = "AVACOM OPS Core"
$VenvName     = "prtvenv01-avacom"
$LauncherName = "Start-AvacomOPSCore.bat"
$PanelExe     = "Avacom.OPS.Master.exe"
$FirewallRule = "AVACOM OPS Core (TCP 8000)"
$LegacyPath   = "C:\AVACOM\ExamCore"   # destino por omision del asistente PowerShell
# Datos escribibles: viven fuera de Program Files porque ahi un usuario estandar
# no puede escribir. Contienen la base con los resultados y los registros.
$DataDir      = Join-Path $env:ProgramData "AVACOM\ExamCore"

$actions = [System.Collections.Generic.List[string]]::new()
$skipped = [System.Collections.Generic.List[string]]::new()

function Write-Section([string] $text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

<#
 Comprueba que la ruta sea de verdad una instalacion antes de borrarla en
 recursivo.

 El parametro -Path lo escribe una persona, y Remove-Item -Recurse -Force sobre
 una raiz de disco o sobre "C:\Program Files" no tiene vuelta atras. Se exige
 que la carpeta contenga al menos una senal del producto y que tenga suficiente
 profundidad para no ser una carpeta de sistema.
#>
function Assert-InstallPath([string] $candidate) {
    # GetFullPath se aplica al texto SIN recortar la barra final. Recortarla antes
    # convierte "C:\" en "C:", y GetFullPath("C:") no devuelve la raiz del disco
    # sino el directorio actual de ese disco: pasar "C:\" acababa apuntando a la
    # carpeta de trabajo, que es exactamente el error que esto debe impedir.
    $resolved = [IO.Path]::GetFullPath($candidate)
    $root     = [IO.Path]::GetPathRoot($resolved)
    $full     = $resolved.TrimEnd('\')

    if ($full.Length -le $root.TrimEnd('\').Length) { throw "Negado: '$resolved' es la raiz de un disco." }

    $depth = ($full.Substring($root.Length).Split('\') | Where-Object { $_ }).Count
    if ($depth -lt 2) { throw "Negado: '$full' esta demasiado arriba para ser una instalacion." }

    foreach ($protected in @($env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramData, $env:USERPROFILE)) {
        if ($protected -and $full -eq $protected.TrimEnd('\')) { throw "Negado: '$full' es una carpeta del sistema." }
    }

    # Un arbol de codigo fuente nunca es un destino de desinstalacion. Se rechaza
    # antes de mirar las senales, porque el repositorio contiene backend\ y
    # confundirlo con una instalacion costaria el trabajo entero.
    foreach ($sourceMarker in @(".git", "*.slnx", "*.sln", "installer\payload")) {
        if (@(Get-ChildItem -Path $full -Filter $sourceMarker -Force -ErrorAction SilentlyContinue).Count -gt 0) {
            throw "Negado: '$full' es un arbol de codigo fuente ($sourceMarker), no una instalacion."
        }
    }

    # Senales que SOLO existen en una instalacion. backend\manage.py queda fuera
    # a proposito: tambien esta en el repositorio, asi que no distingue nada.
    $markers = @("app\$PanelExe", "runtime\python.exe", $LauncherName, "$VenvName\Scripts\python.exe")
    $found = @($markers | Where-Object { Test-Path -LiteralPath (Join-Path $full $_) })
    if ($found.Count -eq 0) {
        throw "Negado: '$full' no parece una instalacion de $ProductName. Se esperaba al menos uno de: $($markers -join ', ')."
    }

    return $full
}

function Do-Step([string] $description, [scriptblock] $action) {
    if ($DryRun) { Write-Host "  [simulado] $description" -ForegroundColor Yellow; return }
    try {
        & $action
        Write-Host "  hecho: $description"
        $actions.Add($description)
    }
    catch {
        Write-Host "  ATENCION: $description -> $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# ── 1. Localizar la instalacion ─────────────────────────────────────────────
Write-Section "Buscando la instalacion"

$registryKey = $null
$uninstallString = $null
foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")) {
    $candidate = Join-Path $hive $AppId
    if (Test-Path $candidate) {
        $registryKey = $candidate
        $properties = Get-ItemProperty $candidate
        $uninstallString = $properties.UninstallString
        if (-not $Path -and $properties.InstallLocation) { $Path = $properties.InstallLocation.TrimEnd('\') }
        Write-Host "  Registrada en Agregar o quitar programas: $($properties.DisplayName)"
        break
    }
}

if (-not $Path -and (Test-Path $LegacyPath)) {
    $Path = $LegacyPath
    Write-Host "  Instalacion del asistente PowerShell: $LegacyPath"
}

if (-not $Path -or -not (Test-Path $Path)) {
    if ($registryKey) {
        Write-Host "  La entrada del registro existe pero la carpeta no. Se limpiara el registro." -ForegroundColor Yellow
    }
    else {
        Write-Host ""
        Write-Host "No se encontro ninguna instalacion de $ProductName." -ForegroundColor Green
        Write-Host "El equipo ya esta listo para instalar una version nueva."
        return
    }
}
else {
    # Se valida ANTES de la confirmacion: si la ruta no sirve, hay que decirlo
    # antes de pedirle a alguien que escriba SI.
    $Path = Assert-InstallPath $Path
    $size = (Get-ChildItem $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    Write-Host ("  Carpeta: {0} ({1:N0} MB)" -f $Path, ($size / 1MB))
}

# ── 2. Confirmacion ─────────────────────────────────────────────────────────
if (-not $Force -and -not $DryRun) {
    Write-Host ""
    Write-Host "Se desinstalara $ProductName de: $Path"
    if ($PurgeData) { Write-Host "Los datos (.env y resultados) se BORRARAN sin respaldo." -ForegroundColor Red }
    else            { Write-Host "Los datos (.env y resultados) se respaldaran antes de borrar." }
    Write-Host "No se tocara Python del sistema, MongoDB ni ningun otro producto."
    $answer = Read-Host "Escribe SI para continuar"
    if ($answer -ne "SI") { Write-Host "Cancelado. No se modifico nada."; return }
}

# ── 3. Detener lo que este en marcha ────────────────────────────────────────
# Sin esto, los archivos en uso no se pueden borrar y la desinstalacion queda a
# medias. Se filtra por RUTA y no por nombre de proceso: matar "python" a secas
# tumbaria el servicio de MongoDB o cualquier script ajeno que este corriendo.
Write-Section "Deteniendo procesos de la instalacion"
if ($Path -and (Test-Path $Path)) {
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($Path, [StringComparison]::OrdinalIgnoreCase)
    }
    if ($running) {
        foreach ($process in $running) {
            Do-Step "detener $($process.ProcessName) (PID $($process.Id))" {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
            }
        }
        Start-Sleep -Seconds 2
    }
    else { Write-Host "  No habia nada corriendo desde la carpeta de instalacion." }
}

# ── 4. Respaldar los datos ──────────────────────────────────────────────────
Write-Section "Datos"
$backupDir = $null
if ($PurgeData) {
    Write-Host "  -PurgeData: no se respalda nada." -ForegroundColor Yellow
}
elseif ($Path -and (Test-Path $Path)) {
    $stamp     = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $env:ProgramData "AVACOM\ExamCore-respaldo-$stamp"
    # La base vive en la carpeta de datos, fuera de Program Files. Se sigue mirando
    # backend\ por si la instalacion es de una version anterior, donde si estaba ahi.
    $toBackup  = @(
        @{ From = Join-Path $Path ".env";                To = ".env" },
        @{ From = Join-Path $DataDir "db.sqlite3";       To = "db.sqlite3" },
        @{ From = Join-Path $Path "backend\db.sqlite3";  To = "db.sqlite3" }
    ) | Where-Object { Test-Path $_.From } | Group-Object To | ForEach-Object { $_.Group[0] }

    if ($toBackup.Count -eq 0) {
        Write-Host "  No hay datos que respaldar."
        $backupDir = $null
    }
    else {
        Do-Step "respaldar $($toBackup.Count) archivo(s) en $backupDir" {
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            foreach ($item in $toBackup) { Copy-Item -LiteralPath $item.From -Destination (Join-Path $backupDir $item.To) -Force }
        }
    }
}

# ── 5. Desinstalador de Inno, si la version se instalo con el Setup.exe ─────
Write-Section "Desinstalacion"
$innoUninstaller = $null
if ($Path -and (Test-Path $Path)) {
    $innoUninstaller = Get-ChildItem $Path -Filter "unins*.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $innoUninstaller -and $uninstallString) {
    # UninstallString viene entre comillas y puede traer parametros.
    $candidate = ($uninstallString -replace '^"([^"]+)".*$', '$1').Trim('"')
    if (Test-Path $candidate) { $innoUninstaller = $candidate }
}

if ($innoUninstaller) {
    Do-Step "ejecutar el desinstalador de Inno ($([IO.Path]::GetFileName($innoUninstaller)))" {
        $process = Start-Process -FilePath $innoUninstaller -Wait -PassThru `
            -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
        # Sin capturar el handle, ExitCode puede venir nulo en Windows PowerShell.
        $null = $process.Handle
        if ($process.ExitCode -ne 0) { throw "el desinstalador devolvio $($process.ExitCode)" }
    }
    Start-Sleep -Seconds 2
}
else {
    Write-Host "  Sin desinstalador de Inno: la instalacion vino del asistente PowerShell."
}

# ── 6. Entorno virtual ──────────────────────────────────────────────────────
# Explicito y con su propio paso, aunque en la mayoria de casos caiga junto con
# la carpeta: el asistente PowerShell lo crea dentro de la instalacion, pero
# conviene que el registro de la desinstalacion diga que se quito.
Write-Section "Entorno virtual"
$venvPath = if ($Path) { Join-Path $Path $VenvName } else { $null }
if ($venvPath -and (Test-Path $venvPath)) {
    Do-Step "borrar el entorno virtual $VenvName" {
        Remove-Item -Recurse -Force -LiteralPath $venvPath -ErrorAction Stop
    }
}
else { Write-Host "  No hay entorno virtual que borrar." }

# ── 7. Restos ───────────────────────────────────────────────────────────────
Write-Section "Restos"

if ($Path -and (Test-Path $Path)) {
    $left = @(Get-ChildItem $Path -Recurse -File -ErrorAction SilentlyContinue)
    if ($left.Count -gt 0) {
        # __pycache__, db.sqlite3 y el .env que el desinstalador de Inno no
        # cubre cuando la instalacion no vino de el.
        Do-Step "borrar la carpeta de instalacion ($($left.Count) archivo(s) restantes)" {
            Remove-Item -Recurse -Force -LiteralPath $Path -ErrorAction Stop
        }
    }
    else {
        Do-Step "borrar la carpeta vacia" { Remove-Item -Recurse -Force -LiteralPath $Path -ErrorAction Stop }
    }
}

foreach ($shortcut in @(
    (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "$ProductName.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "$ProductName.lnk"))) {
    if (Test-Path $shortcut) {
        Do-Step "borrar el acceso directo $([IO.Path]::GetFileName($shortcut))" {
            Remove-Item -LiteralPath $shortcut -Force -ErrorAction Stop
        }
    }
}

$startMenu = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\$ProductName"
if (Test-Path $startMenu) {
    Do-Step "borrar el grupo del menu Inicio" { Remove-Item -Recurse -Force -LiteralPath $startMenu -ErrorAction Stop }
}

# La regla se borra por nombre exacto. netsh devuelve 1 si no existe, asi que se
# comprueba antes en lugar de tratar ese caso como un fallo.
$ruleExists = (& netsh advfirewall firewall show rule name="$FirewallRule" 2>$null | Out-String) -notmatch "(?i)No matches|No hay coincidencias"
if ($ruleExists) {
    Do-Step "borrar la regla de firewall" {
        & netsh advfirewall firewall delete rule name="$FirewallRule" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "netsh devolvio $LASTEXITCODE" }
    }
}
else { Write-Host "  No hay regla de firewall que borrar." }

# La carpeta de datos se borra al final y solo despues del respaldo: contiene los
# resultados de examenes ya rendidos, que no se recuperan.
if (Test-Path $DataDir) {
    Do-Step "borrar la carpeta de datos ($DataDir)" {
        Remove-Item -Recurse -Force -LiteralPath $DataDir -ErrorAction Stop
    }
    $parent = Split-Path -Parent $DataDir
    if ((Test-Path $parent) -and -not (Get-ChildItem $parent -Force -ErrorAction SilentlyContinue)) {
        Do-Step "borrar la carpeta AVACOM vacia" { Remove-Item -Force -LiteralPath $parent -ErrorAction Stop }
    }
}

if ($registryKey -and (Test-Path $registryKey)) {
    Do-Step "borrar la entrada de Agregar o quitar programas" {
        Remove-Item -Recurse -Force -LiteralPath $registryKey -ErrorAction Stop
    }
}

# ── 8. Lo que se dejo intacto ───────────────────────────────────────────────
Write-Section "Intacto, por diseno"
$skipped.Add("Python del sistema (solo se borro el runtime embebido de la instalacion)")

$mongoService = Get-Service -Name "*mongo*" -ErrorAction SilentlyContinue
if ($mongoService) { $skipped.Add("Servicio MongoDB '$($mongoService.Name -join ", ")' y sus datos") }
else { $skipped.Add("MongoDB (no hay servicio en este equipo)") }
$skipped.Add("Volumen mongo_data de Docker")
$skipped.Add("Cualquier otro producto: la busqueda fue por AppId, no por nombre")

foreach ($item in $skipped) { Write-Host "  - $item" }

# ── 9. Resumen ──────────────────────────────────────────────────────────────
Write-Section "Resumen"
if ($DryRun) {
    Write-Host "Simulacion: no se modifico nada. Vuelve a ejecutar sin -DryRun para aplicar." -ForegroundColor Yellow
    return
}

Write-Host "$($actions.Count) accion(es) aplicadas."
if ($backupDir -and (Test-Path $backupDir)) {
    Write-Host ""
    Write-Host "Respaldo de datos en:" -ForegroundColor Green
    Write-Host "  $backupDir"
    Write-Host "Para conservar los resultados en la version nueva, instala primero y luego copia"
    Write-Host "db.sqlite3 a backend\ y .env a la raiz de la instalacion."
}

$stillThere = ($Path -and (Test-Path $Path))
if ($stillThere) {
    Write-Host ""
    Write-Host "ATENCION: la carpeta $Path todavia existe. Suele ser un archivo en uso:" -ForegroundColor Yellow
    Write-Host "cierra el panel del profesor y la consola de la API, y vuelve a ejecutar."
    exit 1
}

Write-Host ""
Write-Host "$ProductName desinstalado. El equipo esta listo para la version nueva." -ForegroundColor Green
