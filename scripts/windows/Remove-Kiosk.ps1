[CmdletBinding(SupportsShouldProcess = $true)]
param([switch] $DisableShellLauncher)

$ErrorActionPreference = "Stop"
if ($PSCmdlet.ShouldProcess("Assigned Access", "Quitar configuración de kiosco")) { Clear-AssignedAccess }
if ($DisableShellLauncher) {
    $shell = [wmiclass]"\\localhost\root\standardcimv2\embedded:WESL_UserSetting"
    if ($PSCmdlet.ShouldProcess("Shell Launcher", "Desactivar")) { $shell.SetEnabled($false) | Out-Null }
}
$marker = Join-Path $env:ProgramData "AVACOM\kiosk-provisioned.marker"
if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
Write-Host "Configuración retirada. El usuario local no fue eliminado. Reinicia el equipo."

