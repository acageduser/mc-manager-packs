@echo off
setlocal enableextensions
title MinecraftManager — Clean Auto Build
cd /d "%~dp0"

rem Build mode: onefile (default) or onefolder via arg
set "MODE=%~1"
if /I "%MODE%"=="" set "MODE=onefile"

echo === [1/7] Clean ===
rmdir /s /q build  2>nul
rmdir /s /q dist   2>nul
del /q MinecraftManager.spec 2>nul

echo.
echo === [2/7] Find Python ===
set "PYTHON_EXE="
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE (
  echo ERROR: Python not found. Install Python 3.11+ and retry.
  pause & exit /b 1
)
echo Using: "%PYTHON_EXE%"

echo.
echo === [3/7] venv ===
if not exist ".venv\Scripts\python.exe" "%PYTHON_EXE%" -m venv .venv
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%PYTHON_EXE%"

echo.
echo === [4/7] Deps ===
"%PY%" -m pip install --upgrade pip
if exist requirements.txt "%PY%" -m pip install -r requirements.txt
"%PY%" -m pip install pyinstaller

echo.
echo === [5/7] Ensure package markers ===
if not exist "app\__init__.py"            type nul > "app\__init__.py"
if not exist "app\ui\__init__.py"         type nul > "app\ui\__init__.py"
if not exist "app\services\__init__.py"   type nul > "app\services\__init__.py"

echo.
echo === [6/7] PyInstaller (%MODE%) ===
set "ICON="
if exist "assets\app.ico" set "ICON=--icon assets\app.ico"

rem NOTE: single line so hidden-imports are actually passed.
set "COMMON_OPTS=--noconfirm --clean --windowed --name MinecraftManager %ICON% --paths . --hidden-import app.ui.main_window --hidden-import app.services.config --hidden-import app.services.github_api --hidden-import app.services.minecraft --hidden-import app.services.threading_worker --hidden-import app.services.secret_store --hidden-import app.services.crypto --hidden-import app.services.logging_util --hidden-import app.services.packer --hidden-import app.services.telemetry"

if /I "%MODE%"=="onefile" (
  "%PY%" -m PyInstaller %COMMON_OPTS% --onefile app\main.py
) else (
  "%PY%" -m PyInstaller %COMMON_OPTS% app\main.py
)

if errorlevel 1 (
  echo Build failed. See errors above.
  pause & exit /b 1
)

echo.
echo === [7/7] Done ===
if /I "%MODE%"=="onefile" (
  echo EXE: %cd%\dist\MinecraftManager.exe
) else (
  echo EXE: %cd%\dist\MinecraftManager\MinecraftManager.exe
)
start "" explorer.exe "%cd%\dist" 2>nul
exit /b 0
