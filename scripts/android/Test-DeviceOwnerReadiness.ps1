<#
.SYNOPSIS
    Comprueba, para cada Android conectado, si `dpm set-device-owner` puede tener exito.

.DESCRIPTION
    Android rechaza set-device-owner si el equipo ya tiene cuentas, un propietario
    previo o usuarios secundarios. Descubrirlo tableta por tableta durante el
    despliegue cuesta horas: este script clasifica el lote completo antes de tocarlo,
    para separar las tabletas listas de las que exigen restablecimiento de fabrica.

    No modifica nada en los dispositivos: solo lee estado.

.EXAMPLE
    .\scripts\android\Test-DeviceOwnerReadiness.ps1
    .\scripts\android\Test-DeviceOwnerReadiness.ps1 -CsvPath .\dist\preflight.csv
#>
[CmdletBinding()]
param(
    [string] $Adb = "adb",
    [string] $CsvPath
)

$ErrorActionPreference = "Stop"
$package = "com.avacom.student"

& $Adb start-server | Out-Null
$serials = @(& $Adb devices | Select-Object -Skip 1 |
    Where-Object { $_ -match "^(\S+)\s+device$" } |
    ForEach-Object { $Matches[1] })

if ($serials.Count -eq 0) { throw "No hay dispositivos autorizados por ADB. Revisa el cable/emparejamiento y la ventana de autorizacion en cada tableta." }
Write-Host "Dispositivos detectados: $($serials.Count)"

$resultados = @(foreach ($serial in $serials) {
    # Cada consulta se aisla: una tableta que se desconecta a mitad del lote no debe
    # abortar el diagnostico de las demas.
    function Get-Shell([string] $comando) {
        try { (& $Adb -s $serial shell $comando 2>&1 | Out-String).Trim() } catch { "" }
    }

    $modelo      = Get-Shell "getprop ro.product.model"
    $version     = Get-Shell "getprop ro.build.version.release"
    $owners      = Get-Shell "dpm list-owners"
    $cuentas     = Get-Shell "dumpsys account"
    $usuarios    = Get-Shell "pm list users"
    $instalado   = Get-Shell "pm list packages $package"

    # "Accounts: 0" es la linea que expone dumpsys; si no aparece, se cae al conteo
    # de lineas Account{...}, porque el formato cambia entre versiones de Android.
    $numCuentas = if ($cuentas -match "Accounts:\s*(\d+)") { [int]$Matches[1] }
                  else { ([regex]::Matches($cuentas, "Account\s*\{")).Count }

    $numUsuarios = ([regex]::Matches($usuarios, "UserInfo\{")).Count
    $tieneOwner  = $owners -notmatch "(?i)no device owner" -and $owners -match "(?i)$package|admin"

    $bloqueos = @()
    if ($numCuentas -gt 0)  { $bloqueos += "$numCuentas cuenta(s) configurada(s)" }
    if ($numUsuarios -gt 1) { $bloqueos += "$numUsuarios usuarios en el equipo" }
    if ($tieneOwner)        { $bloqueos += "ya existe un device owner" }

    [pscustomobject]@{
        Serial       = $serial
        Modelo       = $modelo
        Android      = $version
        Cuentas      = $numCuentas
        Usuarios     = $numUsuarios
        OwnerActual  = if ($owners) { ($owners -split "`n")[-1].Trim() } else { "(sin dato)" }
        AppInstalada = [bool]$instalado
        Listo        = ($bloqueos.Count -eq 0)
        Bloqueo      = if ($bloqueos.Count -eq 0) { "" } else { $bloqueos -join "; " }
    }
})

$resultados | Format-Table Serial, Modelo, Android, Cuentas, Usuarios, AppInstalada, Listo, Bloqueo -AutoSize

$listos = @($resultados | Where-Object Listo)
Write-Host ""
Write-Host "Listos para set-device-owner : $($listos.Count) de $($resultados.Count)"
if ($listos.Count -lt $resultados.Count) {
    Write-Warning "Las tabletas con bloqueo necesitan restablecimiento de fabrica (o quitar cuentas y usuarios) antes de aprovisionar."
}

if ($CsvPath) {
    $resultados | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8
    Write-Host "Informe: $CsvPath"
}
