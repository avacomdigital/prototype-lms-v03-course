<#
.SYNOPSIS
    Aprovisiona Device Owner en TODAS las tabletas conectadas por ADB, en paralelo.

.DESCRIPTION
    Provision-DeviceOwner.ps1 exige exactamente un dispositivo, lo que obliga a
    conectar y desconectar cien veces. Este script recorre el lote completo:
    instala el APK, ejecuta `dpm set-device-owner`, verifica con `dpm list-owners`
    y deja un CSV con el resultado de cada serial.

    Cada tableta corre en su propio job: el cuello de botella es la copia del APK,
    y serializarla desperdicia el ancho de banda del hub USB.

    Una tableta que falla no detiene el lote; queda marcada como Fallo en el CSV con
    la salida de ADB, que es lo que dice si el problema fue una cuenta presente o un
    APK sin firmar.

.EXAMPLE
    .\scripts\android\Provision-DeviceOwnerBatch.ps1 -ApkPath .\dist\AvacomStudent-arm64.apk
    .\scripts\android\Provision-DeviceOwnerBatch.ps1 -ApkPath .\dist\AvacomStudent-arm64.apk -MaxParalelo 4 -CsvPath .\dist\lote-01.csv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ApkPath,
    [string] $Adb = "adb",
    [int]    $MaxParalelo = 8,
    [string] $CsvPath,
    [switch] $SkipInstall,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$package   = "com.avacom.student"
$component = "$package/com.avacom.student.ExamDeviceAdminReceiver"

$resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path
$resolvedAdb = (Get-Command $Adb -ErrorAction Stop).Source

& $resolvedAdb start-server | Out-Null
$serials = @(& $resolvedAdb devices | Select-Object -Skip 1 |
    Where-Object { $_ -match "^(\S+)\s+device$" } |
    ForEach-Object { $Matches[1] })

if ($serials.Count -eq 0) { throw "No hay dispositivos autorizados por ADB." }

Write-Host "APK        : $resolvedApk"
Write-Host "Componente : $component"
Write-Host "Tabletas   : $($serials.Count) (hasta $MaxParalelo en paralelo)"
Write-Host ""

if (-not $Force) {
    Write-Warning "set-device-owner es irreversible sin restablecimiento de fabrica y falla si la tableta tiene cuentas."
    $respuesta = Read-Host "Escribe SI para aprovisionar las $($serials.Count) tabletas detectadas"
    if ($respuesta -ne "SI") { Write-Host "Cancelado. No se toco ningun dispositivo."; return }
}

# El job recibe todo por argumento: no hereda el ambito del script padre.
$trabajo = {
    param($adb, $serial, $apk, $package, $component, $skipInstall)

    function Invoke-Adb {
        param([string[]] $argumentos)
        $salida = & $adb -s $serial @argumentos 2>&1 | Out-String
        [pscustomobject]@{ Codigo = $LASTEXITCODE; Salida = $salida.Trim() }
    }

    $modelo = (Invoke-Adb @("shell", "getprop", "ro.product.model")).Salida

    if (-not $skipInstall) {
        $instalacion = Invoke-Adb @("install", "-r", $apk)
        if ($instalacion.Codigo -ne 0 -or $instalacion.Salida -notmatch "Success") {
            return [pscustomobject]@{ Serial = $serial; Modelo = $modelo; Estado = "Fallo"; Etapa = "install"; Detalle = $instalacion.Salida }
        }
    }

    $owner = Invoke-Adb @("shell", "dpm", "set-device-owner", $component)
    if ($owner.Salida -notmatch "(?i)Success") {
        return [pscustomobject]@{ Serial = $serial; Modelo = $modelo; Estado = "Fallo"; Etapa = "set-device-owner"; Detalle = $owner.Salida }
    }

    # No basta con que set-device-owner responda Success: se confirma leyendo el
    # propietario efectivo, que es lo que consulta IsDeviceOwnerApp en la app.
    $lista = Invoke-Adb @("shell", "dpm", "list-owners")
    if ($lista.Salida -notmatch [regex]::Escape($package)) {
        return [pscustomobject]@{ Serial = $serial; Modelo = $modelo; Estado = "Fallo"; Etapa = "verificacion"; Detalle = "list-owners no reporta $package -> $($lista.Salida)" }
    }

    [pscustomobject]@{ Serial = $serial; Modelo = $modelo; Estado = "Listo"; Etapa = "completo"; Detalle = $lista.Salida }
}

$jobs = @()
foreach ($serial in $serials) {
    while (@(Get-Job -State Running).Count -ge $MaxParalelo) { Start-Sleep -Milliseconds 500 }
    $jobs += Start-Job -Name $serial -ScriptBlock $trabajo -ArgumentList $resolvedAdb, $serial, $resolvedApk, $package, $component, [bool]$SkipInstall
    Write-Host "  -> lanzado $serial"
}

Write-Host ""
Write-Host "Esperando a que termine el lote..."
$null = Wait-Job -Job $jobs
$resultados = @(Receive-Job -Job $jobs)
Remove-Job -Job $jobs

$resultados | Sort-Object Estado, Serial | Format-Table Serial, Modelo, Estado, Etapa, Detalle -AutoSize -Wrap

$listos  = @($resultados | Where-Object Estado -eq "Listo")
$fallos  = @($resultados | Where-Object Estado -eq "Fallo")
Write-Host ""
Write-Host "Aprovisionadas : $($listos.Count)"
Write-Host "Con fallo      : $($fallos.Count)"

if ($CsvPath) {
    $resultados | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8
    Write-Host "Informe        : $CsvPath"
}

if ($fallos.Count -gt 0) {
    Write-Warning "Revisa la columna Detalle: 'Not allowed to set the device owner' significa que la tableta tiene cuentas o usuarios y necesita restablecimiento de fabrica."
    exit 1
}
