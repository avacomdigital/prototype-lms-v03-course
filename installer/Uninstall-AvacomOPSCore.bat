@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Desinstalar AVACOM OPS Core

rem ============================================================================
rem  Punto de entrada del desinstalador. Se eleva y cede el control al script
rem  de PowerShell, que es donde vive la logica.
rem
rem  Se usa para preparar el equipo antes de instalar una version nueva.
rem  NO desinstala Python del sistema ni toca MongoDB.
rem ============================================================================

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%Uninstall-AvacomOPSCore.ps1"

echo.
echo   AVACOM OPS Core - Desinstalador
echo   --------------------------------
echo.

if not exist "%PS1%" (
    echo   [X] No se encontro Uninstall-AvacomOPSCore.ps1 junto a este archivo.
    pause
    exit /b 1
)

rem Borrar de Program Files, quitar la regla de firewall y tocar HKLM piden admin.
net session >nul 2>&1
if errorlevel 1 (
    echo   Se requieren permisos de administrador. Windows pedira confirmacion...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RESULT=%ERRORLEVEL%"

echo.
if "%RESULT%"=="0" (
    echo   Listo. Ya puedes ejecutar el Setup.exe de la version nueva.
) else (
    echo   El desinstalador termino con codigo %RESULT%. Revisa los mensajes de arriba.
)
pause
exit /b %RESULT%
