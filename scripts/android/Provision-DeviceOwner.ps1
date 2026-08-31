[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ApkPath,
    [string] $Adb = "adb",
    [switch] $SkipInstall
)

$ErrorActionPreference = "Stop"
$package = "com.avacom.student"
$component = "$package/com.avacom.student.ExamDeviceAdminReceiver"
$resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path

& $Adb start-server | Out-Null
$devices = @(& $Adb devices | Select-Object -Skip 1 | Where-Object { $_ -match "\tdevice$" })
if ($devices.Count -ne 1) { throw "Debe haber exactamente un dispositivo Android autorizado por ADB. Detectados: $($devices.Count)." }

if (-not $SkipInstall) {
    & $Adb install -r $resolvedApk
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar el APK." }
}

Write-Host "Configurando Device Owner. El equipo debe estar recién restablecido, sin cuentas ni perfil de trabajo."
& $Adb shell dpm set-device-owner $component
if ($LASTEXITCODE -ne 0) {
    throw "Falló Device Owner. Restablece el equipo a fábrica, no agregues cuentas, habilita ADB y repite."
}

& $Adb shell dpm list-owners
Write-Host "Aprovisionamiento completado para $package. Abre la app y valida el inicio del examen."

