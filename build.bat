@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Сначала пробуем py (лаунчер Windows), потом python
set PYCMD=
where py >nul 2>&1 && set PYCMD=py -3
if not defined PYCMD where python >nul 2>&1 && set PYCMD=python
if not defined PYCMD (
    echo Python not found. Install Python and add it to PATH, or run: py -3 -m pip install pyinstaller
    echo Then: py -3 -m PyInstaller FundingRate.spec --noconfirm
    pause
    exit /b 1
)

echo Using: %PYCMD%
echo.

echo Installing dependencies (uvicorn, fastapi, etc.)...
%PYCMD% -m pip install -r requirements.txt -q --no-warn-script-location
if errorlevel 1 (
    echo Pip install failed.
    pause
    exit /b 1
)

echo Installing PyInstaller if needed...
%PYCMD% -m pip install pyinstaller -q --no-warn-script-location

echo Building FundingRate.exe ...
%PYCMD% -m PyInstaller FundingRate.spec --noconfirm
if errorlevel 1 (
    echo PyInstaller failed.
    pause
    exit /b 1
)

if exist "dist\FundingRate.exe" (
    echo.
    echo Done. EXE: dist\FundingRate.exe
    echo You can copy it anywhere and run.
) else (
    echo Build failed - dist\FundingRate.exe not found.
)

echo.
pause
