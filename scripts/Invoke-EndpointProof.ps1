<#
.SYNOPSIS
    Ejecuta la prueba integral del prototipo de cursos contra un Master en marcha.

.DESCRIPTION
    Recorre el contrato HTTP y WebSocket como lo haría un dispositivo real:
    abre el curso, valida su jerarquía, asigna un estudiante, realiza el quiz,
    consulta el consolidado y verifica la pregunta actual por WebSocket.

    Úsalo al llegar a una sede, después de levantar la API y antes de repartir los
    dispositivos: confirma que la red, el firewall y el curso demo
    están correctos.

.EXAMPLE
    .\scripts\Invoke-EndpointProof.ps1
    Verifica el Master local en http://127.0.0.1:8000.

.EXAMPLE
    .\scripts\Invoke-EndpointProof.ps1 -BaseUrl http://192.168.1.10:8000
    Verifica el Master de la sede desde otro equipo de la LAN.

.NOTES
    Agrega una inscripción y un intento identificados como PoC. El curso CRUD
    temporal se elimina al finalizar.
#>
[CmdletBinding()]
param(
    [string] $BaseUrl = "http://127.0.0.1:8000",
    [string] $Python = "",
    [switch] $SkipWebSocket
)

# Ver la nota de Invoke-Tests.ps1: en PowerShell 5.1 el stderr de un proceso nativo
# no debe tratarse como error terminante.
$ErrorActionPreference = "Continue"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$proofScript = Join-Path $repositoryRoot "backend\tools\endpoint_proof.py"

if (-not (Test-Path -LiteralPath $proofScript)) {
    throw "No se encontró $proofScript. Ejecuta el script desde el repositorio clonado."
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $candidates = @(
        (Join-Path $repositoryRoot ".venv\Scripts\python.exe"),
        (Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe")
    )
    $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $Python) { $Python = "python" }
}

Write-Host "Intérprete: $Python"
Write-Host "Master:     $BaseUrl"
Write-Host ""

$arguments = @($proofScript, "--base-url", $BaseUrl)
if ($SkipWebSocket) { $arguments += "--skip-websocket" }

& $Python @arguments
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Prueba superada: OPS Master está listo para el curso y el quiz." -ForegroundColor Green
} else {
    Write-Host "La prueba de concepto encontró fallas. Revisa el detalle anterior." -ForegroundColor Red
}
exit $exitCode
