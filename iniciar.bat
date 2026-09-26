@echo off
title Sistema de Cobros
cd /d "%~dp0"
echo ============================================
echo   SISTEMA DE COBROS - iniciando...
echo ============================================

rem ---------- Buscar el entorno virtual de este PC ----------
rem La ruta que manda vive en una carpeta LOCAL de este PC (no la toca OneDrive).
rem instalar_venv.bat escribe esa ruta; el archivo entorno_venv.txt del
rem proyecto es solo referencia porque OneDrive lo sincroniza entre PCs.
set "VENVDIR="
if exist "%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt" set /p VENVDIR=<"%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt"
if not defined VENVDIR if exist "entorno_venv.txt" set /p VENVDIR=<entorno_venv.txt
if not defined VENVDIR if exist "C:\EntornosPython\SistemaCobros-venv\Scripts\python.exe" set "VENVDIR=C:\EntornosPython\SistemaCobros-venv"

rem ---------- Evitar doble arranque: si el puerto 5001 ya esta ocupado, avisar ----------
:puerto
netstat -ano | findstr ":5001 " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto venv_check
echo.
echo [AVISO] El puerto 5001 ya esta en uso. Probablemente ya hay un Sistema
echo         de Cobros abierto en otra ventana, o quedo uno abierto de antes.
echo         Busca la ventana negra en la barra de tareas y usalo desde ahi,
echo         o cierra esa ventana y vuelve a correr este archivo.
echo.
pause
exit /b 1

:venv_check
if defined VENVDIR if exist "%VENVDIR%\Scripts\python.exe" goto venv_ok

echo.
echo No encuentro el entorno virtual de este PC.
echo Solucion: doble clic a instalar_venv.bat (esta junto a este archivo),
echo elige la carpeta donde guardarlo y vuelve a correr INICIAR.bat.
echo.
pause
exit /b 1

:venv_ok
echo Entorno: %VENVDIR%
echo.
echo Abre en tu navegador:  http://localhost:5001
echo (Esta ventana debe quedar abierta mientras usas el sistema)
echo.
start "" http://localhost:5001
"%VENVDIR%\Scripts\python.exe" run.py
pause
