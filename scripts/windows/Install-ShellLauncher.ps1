[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)] [string] $KioskUser,
    [Parameter(Mandatory = $true)] [string] $ExecutablePath
)

$ErrorActionPreference = "Stop"
$edition = (Get-ComputerInfo -Property WindowsProductName).WindowsProductName
if ($edition -notmatch "Enterprise|Education|IoT") { throw "Shell Launcher solo está disponible en Enterprise, Education o IoT Enterprise. Edición detectada: $edition" }
$resolvedExe = (Resolve-Path -LiteralPath $ExecutablePath).Path
$user = Get-LocalUser -Name $KioskUser -ErrorAction Stop

Enable-WindowsOptionalFeature -Online -FeatureName Client-EmbeddedShellLauncher -All -NoRestart | Out-Null
$shell = [wmiclass]"\\localhost\root\standardcimv2\embedded:WESL_UserSetting"
if ($PSCmdlet.ShouldProcess($KioskUser, "Asignar Shell Launcher a $resolvedExe")) {
    $result = $shell.SetCustomShell($user.SID.Value, $resolvedExe, $null, $null, 0)
    if ($result.ReturnValue -ne 0) { throw "WESL SetCustomShell devolvió $($result.ReturnValue)." }
    $shell.SetEnabled($true) | Out-Null
    $markerDirectory = Join-Path $env:ProgramData "AVACOM"
    New-Item -ItemType Directory -Path $markerDirectory -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $markerDirectory "kiosk-provisioned.marker") -Value "ShellLauncher`n$resolvedExe`n$(Get-Date -Format o)" -Encoding utf8
}
Write-Host "Shell Launcher configurado. Reinicia el equipo para aplicarlo."

