[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $KioskUser = "AvacomStudent",
    [Parameter(Mandatory = $true)] [string] $AppUserModelId,
    [securestring] $KioskPassword
)

$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw "Ejecuta este script en PowerShell como administrador." }

$edition = (Get-ComputerInfo -Property WindowsProductName).WindowsProductName
Write-Host "Edición detectada: $edition"
if ($edition -notmatch "Pro|Enterprise|Education|IoT") { throw "Esta edición no declara compatibilidad con Assigned Access. Revisa la licencia del equipo." }

if (-not (Get-LocalUser -Name $KioskUser -ErrorAction SilentlyContinue)) {
    if (-not $KioskPassword) { $KioskPassword = Read-Host "Contraseña local para $KioskUser" -AsSecureString }
    if ($PSCmdlet.ShouldProcess($KioskUser, "Crear usuario local estándar")) {
        New-LocalUser -Name $KioskUser -Password $KioskPassword -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
    }
}

Write-Warning "Antes de continuar, inicia sesión una vez como $KioskUser e instala el MSIX de AVACOM Student para ese usuario. Luego vuelve como administrador."
if ($PSCmdlet.ShouldProcess($KioskUser, "Configurar Assigned Access con AUMID $AppUserModelId")) {
    Set-AssignedAccess -UserName $KioskUser -AppUserModelId $AppUserModelId
    $markerDirectory = Join-Path $env:ProgramData "AVACOM"
    New-Item -ItemType Directory -Path $markerDirectory -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $markerDirectory "kiosk-provisioned.marker") -Value "AssignedAccess`n$AppUserModelId`n$(Get-Date -Format o)" -Encoding utf8
}

Write-Host "Assigned Access configurado. Reinicia y entra con $KioskUser. Para recuperación usa Ctrl+Alt+Supr y una cuenta administradora."

