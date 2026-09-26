@echo off
title Sistema de Cobros - Instalador del entorno virtual
cd /d "%~dp0"

echo ============================================
echo   SISTEMA DE COBROS - INSTALADOR DEL ENTORNO
echo ============================================
echo.
echo Este instalador crea el entorno virtual (venv) de Python en una carpeta
echo LOCAL de este PC, fuera de OneDrive, para que tus respaldos no se inflen.
echo El codigo y la base de datos si quedan en OneDrive como siempre.
echo.

if not exist "requirements.txt" (
    echo [ERROR] No se encontro requirements.txt junto a este instalador.
    echo         Ejecutalo desde la carpeta del Sistema de Cobros.
    pause
    exit /b 1
)

if exist "venv\Scripts\python.exe" (
    echo [AVISO] Existe una carpeta "venv" vieja dentro del proyecto.
    echo         El sistema ya NO la usa. Puedes borrarla para liberar espacio.
    echo.
)

rem ---------- 1. Buscar un Python disponible ----------
set "PYEXE="
set "PYDESC="
if exist "C:\Python313\python.exe" ( set "PYEXE=C:\Python313\python.exe" & set "PYDESC=C:\Python313\python.exe" )
if not defined PYEXE if exist "C:\Python314\python.exe" ( set "PYEXE=C:\Python314\python.exe" & set "PYDESC=C:\Python314\python.exe" )
if not defined PYEXE (
    py -3 -c "print()" >nul 2>&1 && set "PYEXE=py -3" && set "PYDESC=py launcher - Python 3"
)
if not defined PYEXE (
    python -c "print()" >nul 2>&1 && set "PYEXE=python" && set "PYDESC=python del PATH"
)
if not defined PYEXE (
    echo [ERROR] No se encontro Python en este PC.
    echo         Instala Python 3 desde https://www.python.org/downloads/
    echo         y activa "Add python.exe to PATH" durante la instalacion.
    pause
    exit /b 1
)
echo Python encontrado: %PYDESC%
echo.

rem ---------- 2. Elegir carpeta del venv ----------
:elegir
echo Donde quieres guardar el entorno virtual de ESTE PC?
echo Deja la sugerencia si no tienes preferencia. IMPORTANTE: que sea una
echo carpeta FUERA de OneDrive o de Documentos sincronizados.
echo.
set "VENVDIR=C:\EntornosPython\SistemaCobros-venv"
set /p VENVDIR=Carpeta del venv [Enter = usar la sugerencia]:
set "VENVDIR=%VENVDIR:"=%"

echo %VENVDIR% | findstr /i "onedrive" >nul
if not errorlevel 1 (
    echo [AVISO] Esa carpeta parece estar dentro de OneDrive.
    choice /C SN /M "Continuar de todos modos? S=si N=no"
    if errorlevel 2 goto elegir
)

echo.
echo Resumen:
echo   Python:  %PYDESC%
echo   Venv en: %VENVDIR%
choice /C SN /M "Instalar con estos datos? S=si N=no"
if errorlevel 2 (
    echo Cancelado. No se hizo ningun cambio.
    pause
    exit /b 1
)

rem ---------- 3. Crear el venv ----------
echo.
echo Creando el entorno virtual...
%PYEXE% -m venv "%VENVDIR%"
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno en %VENVDIR%
    pause
    exit /b 1
)

rem ---------- 4. Anotar la ruta para INICIAR.bat ----------
> "entorno_venv.txt" echo %VENVDIR%
echo Ruta anotada en entorno_venv.txt
if not exist "%LOCALAPPDATA%\SistemaCobros" mkdir "%LOCALAPPDATA%\SistemaCobros"
> "%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt" echo %VENVDIR%
echo Ruta anotada tambien localmente en %%LOCALAPPDATA%%\SistemaCobros (esa es la que manda en este PC)

rem ---------- 5. Instalar dependencias ----------
echo Instalando dependencias: Flask, Flask-SQLAlchemy, openpyxl, reportlab, pywin32...
"%VENVDIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENVDIR%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias. Revisa tu conexion a
    echo         internet y vuelve a ejecutar este instalador.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   INSTALACION COMPLETADA
echo ============================================
echo   Entorno virtual: %VENVDIR%
echo.
echo   Cierra esta ventana y usa INICIAR.bat para arrancar el sistema.
echo ============================================
pause
