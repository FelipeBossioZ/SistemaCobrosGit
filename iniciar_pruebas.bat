@echo off
title Sistema de Cobros - PRUEBAS (puerto 777)
cd /d "%~dp0"
set VENV=C:\EntornosPython\SistemaCobros-venv
if exist "%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt" set /p VENV=<"%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt"
echo Entorno: %VENV%
echo ================================================
echo  SISTEMA DE PRUEBAS  ->  http://127.0.0.1:777
echo  (produccion sigue en 5001, no se toca)
echo ================================================
start "" http://127.0.0.1:777
"%VENV%\Scripts\python.exe" run_pruebas.py
pause
