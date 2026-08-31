@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Instalador AVACOM OPS Core

rem ============================================================================
rem  Punto de entrada del instalador.
rem
rem  Este BAT hace la verificacion minima del equipo (lo que puede romperse
rem  ANTES de que exista ninguna interfaz) y luego cede el control al asistente
rem  grafico de PowerShell. Todo lo demas -Python, venv, requirements, exe- lo
rem  hace el asistente, donde cada paso puede mostrarse y reintentarse.
rem ============================================================================

set "SCRIPT_DIR=%~dp0"
set "WIZARD=%SCRIPT_DIR%AvacomOPSCoreSetup.ps1"

echo.
echo   AVACOM OPS Core - Instalador del prototipo
echo   -------------------------------------------
echo.

rem --- 1. PowerShell disponible (viene con Windows 10/11; si falta, nada funciona)
where powershell >nul 2>&1
if errorlevel 1 (
    echo   [X] Este equipo no tiene Windows PowerShell. No es posible continuar.
    pause
    exit /b 1
)
echo   [OK] Windows PowerShell disponible

rem --- 2. El asistente esta junto a este BAT
if not exist "%WIZARD%" (
    echo   [X] No se encontro AvacomOPSCoreSetup.ps1 junto a este instalador.
    echo       Copia la carpeta "installer" completa, no solo el BAT.
    pause
    exit /b 1
)
echo   [OK] Asistente de instalacion encontrado

rem --- 3. winget disponible (lo usa el asistente para instalar Python si falta)
where winget >nul 2>&1
if errorlevel 1 (
    echo   [!] winget no esta disponible. Si Python 3.12.10 ya esta instalado,
    echo       la instalacion continuara; si no, fallara en ese paso.
) else (
    echo   [OK] winget disponible
)

rem --- 4. Elevacion: winget --scope machine y escribir en C:\AVACOM piden admin.
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Se requieren permisos de administrador. Windows pedira confirmacion...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)
echo   [OK] Ejecutando como administrador

echo.
echo   Abriendo el asistente de instalacion...
rem -STA es obligatorio: WinForms no funciona en el apartment MTA por defecto.
powershell -NoProfile -ExecutionPolicy Bypass -STA -File "%WIZARD%"
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
    echo.
    echo   El asistente termino con codigo %RESULT%.
    pause
)
exit /b %RESULT%
