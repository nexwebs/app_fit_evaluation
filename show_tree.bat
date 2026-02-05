@echo off
setlocal EnableDelayedExpansion

:: ---- CONFIG ----
set "START_PATH=."
set EXCLUDES=.venv __pycache__ .git others node_modules

echo.
echo Estructura de carpetas (modo profesional)
echo ==========================================
echo.

call :show_tree "%START_PATH%" 0

echo.
exit /b


:show_tree
set "path=%~1"
set /a depth=%2

:: Crear indentación
set "indent="
for /L %%i in (1,1,%depth%) do set "indent=!indent!    "

:: Listar directorios primero
for /f "delims=" %%D in ('dir /b /ad "%path%" 2^>nul') do (
    set "skip="
    for %%E in (%EXCLUDES%) do (
        if /I "%%D"=="%%E" set "skip=1"
    )
    if not defined skip (
        echo !indent!+-- %%D/
        call :show_tree "%path%\%%D" !depth!+1
    )
)

:: Listar archivos
for /f "delims=" %%F in ('dir /b /a-d "%path%" 2^>nul') do (
    set "skip="
    for %%E in (%EXCLUDES%) do (
        if /I "%%F"=="%%E" set "skip=1"
    )
    if not defined skip (
        echo !indent!+-- %%F
    )
)

exit /b
