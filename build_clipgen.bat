@echo off
title ClipGen Builder
cls

:: --- ВАЖНО: Переходим в папку, где лежит этот скрипт ---
cd /d "%~dp0"

echo ==========================================
echo      STARTING BUILD PROCESS
echo ==========================================
echo.

:: --- Шаг 1: Очистка старых сборок ---
echo [1/3] Cleaning up previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "ClipGen.spec" del /q "ClipGen.spec"
echo Cleanup complete.
echo.

:: --- Шаг 2: Запуск PyInstaller ---
echo [2/3] Building ClipGen.exe...
echo Please wait...
echo.

:: Добавлен флаг --clean для очистки кэша PyInstaller
:: Убедись, что ClipGen.ico - это НАСТОЯЩИЙ .ico файл, а не переименованный png!
py -m PyInstaller --noconsole --onefile --clean --name "ClipGen" --icon="ClipGen.ico" --add-data "lang;lang" --add-data "ClipGen.ico;." ClipGen.py

:: --- Шаг 3: Проверка результата ---
if errorlevel 1 (
    color 4
    echo.
    echo ========================================
    echo  !!! BUILD FAILED !!!
    echo  Something went wrong.
    echo ========================================
    pause
    exit /b
) else (
    color 2
    echo.
    echo ========================================
    echo  BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Your file is located in the 'dist' folder.
    
    :: Удаляем мусорный spec файл
    if exist "ClipGen.spec" del /q "ClipGen.spec"
    
    :: --- ЛАЙФХАК ДЛЯ ПРОВОДНИКА WINDOWS ---
    :: Переименовываем файл, чтобы Windows сбросил кэш иконки и показал новую
    echo Renaming file to force icon update...
    cd dist
    if exist "ClipGen.exe" ren "ClipGen.exe" "ClipGen_v2.exe"
    echo.
    echo Done! Run "dist\ClipGen_v2.exe" to test.
)

echo.
pause