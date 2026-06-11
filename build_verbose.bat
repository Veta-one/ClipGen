@echo off
title ClipGen Verbose Builder
:: Не очищаем экран, чтобы вся история была видна
:: cls

cd /d "%~dp0"

echo ==========================================
echo   ClipGen — VERBOSE BUILD (with realtime logs)
echo ==========================================
echo Build log: %~dp0build.log
echo Press Ctrl+C to abort.
echo.

:: --- Шаг 1: Очистка старых сборок ---
:: Не сносим dist целиком — там лежит папка Models/ с кешем Whisper
:: (3+ ГБ), пользователь не хочет её перекачивать. Удаляем только ClipGen.exe
:: и всю папку build/.
echo [1/3] Cleaning previous builds (keeping dist\Models\)...
if exist "dist\ClipGen.exe" del /q "dist\ClipGen.exe"
if exist "build" rmdir /s /q "build"
if exist "build.log" del /q "build.log"
echo Cleanup complete.
echo.

:: --- Шаг 2: PyInstaller с двойным выводом (консоль + файл) ---
echo [2/3] Running PyInstaller...
echo You will see every line as it happens. Logs also tee'd to build.log.
echo.

:: PowerShell Tee-Object показывает строки в консоли И пишет в файл одновременно.
:: 2>&1 склеивает stderr со stdout, чтобы предупреждения тоже были видны.
powershell -NoProfile -Command "& py -m PyInstaller --clean 'ClipGen.spec' 2>&1 | Tee-Object -FilePath build.log; exit $LASTEXITCODE"

if errorlevel 1 (
    color 4
    echo.
    echo ========================================
    echo  !!! BUILD FAILED !!!
    echo ========================================
    echo  See build.log for full details.
    pause
    exit /b
) else (
    color 2
    echo.
    echo ========================================
    echo  BUILD SUCCESSFUL!
    echo ========================================
    echo  File: dist\ClipGen.exe
    cd dist
    if exist "ClipGen.exe" (
        ren "ClipGen.exe" "ClipGen.exe"
        echo  Size:
        dir /b "ClipGen.exe"
    )
)

echo.
echo Done. Press any key to close...
pause
