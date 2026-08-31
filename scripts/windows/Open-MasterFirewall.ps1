<#
.SYNOPSIS
    Abre el puerto de la API del Master para que los dispositivos de la LAN lleguen.

.DESCRIPTION
    Crea una regla de entrada para el perfil de red Privada únicamente. Si la red
    activa está marcada como Pública, la regla existe pero NO se aplica: el síntoma es
    que la API responde en el propio Master y los dispositivos no la alcanzan, sin
    ningún mensaje de error. Por eso el script comprueba el perfil y avisa.

.EXAMPLE
    .\scripts\windows\Open-MasterFirewall.ps1 -Port 8000

.EXAMPLE
    .\scripts\windows\Open-MasterFirewall.ps1 -Port 8000 -SetNetworkPrivate
    Marca además la red activa como Privada, requisito para que la regla surta efecto.
#>
[CmdletBinding()]
param(
    [int] $Port = 8000,
    [switch] $SetNetworkPrivate
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Ejecuta PowerShell como administrador."
}

# La regla es para el perfil Privado. Si la red está en Público no aplica, así que se
# revisa antes: es la causa más común de "la API funciona en el Master pero la tablet no".
$publicas = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.NetworkCategory -eq 'Public' })

if ($publicas.Count -gt 0) {
    if ($SetNetworkPrivate) {
        foreach ($perfil in $publicas) {
            Set-NetConnectionProfile -InterfaceIndex $perfil.InterfaceIndex -NetworkCategory Private
            Write-Host "Red '$($perfil.Name)' ($($perfil.InterfaceAlias)) marcada como Privada." -ForegroundColor Green
        }
    } else {
        Write-Warning "Estas redes están marcadas como Públicas y la regla no se les aplicará:"
        foreach ($perfil in $publicas) {
            Write-Warning "   $($perfil.Name) en $($perfil.InterfaceAlias)"
        }
        Write-Warning "Vuelve a ejecutar con -SetNetworkPrivate, o cámbialas a Privada en Configuración de red."
    }
}

New-NetFirewallRule -DisplayName "AVACOM OPS Master API" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private -ErrorAction SilentlyContinue | Out-Null
Write-Host "Puerto TCP $Port habilitado para el perfil de red Privada."

# La dirección exacta que hay que escribir en cada dispositivo.
$lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -eq 'Dhcp' } |
    Select-Object -First 1 -ExpandProperty IPAddress
if ($lan) {
    Write-Host ""
    Write-Host "Escribe esta dirección en los dispositivos: http://${lan}:$Port/" -ForegroundColor Green
    Write-Host "Compruébala desde otro equipo abriendo http://${lan}:$Port/health/"
}
