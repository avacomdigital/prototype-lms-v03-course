<#
.SYNOPSIS
    Calcula el checksum del APK en el formato que exige el aprovisionamiento por QR.

.DESCRIPTION
    Android espera un SHA-256 codificado en Base64 URL-safe y sin relleno, tal como se
    documenta para PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM.

    Nota de implementación: se usa SHA256::Create() y ComputeHash en lugar del método
    estático SHA256::HashData, porque éste sólo existe en .NET 5 o superior y Windows
    PowerShell 5.1 corre sobre .NET Framework, donde el script fallaba con
    "no contiene ningún método llamado 'HashData'".

.EXAMPLE
    .\scripts\android\Get-ApkChecksum.ps1 -ApkPath .\dist\AvacomStudent-arm64.apk
#>
[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string] $ApkPath)

$resolved = (Resolve-Path -LiteralPath $ApkPath).Path

$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $stream = [System.IO.File]::OpenRead($resolved)
    try { $hashBytes = $sha256.ComputeHash($stream) }
    finally { $stream.Dispose() }
}
finally { $sha256.Dispose() }

[Convert]::ToBase64String($hashBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
