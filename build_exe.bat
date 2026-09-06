@echo off
chcp 65001 >nul
title Building Altium DbLib Manager Executable

cd /d "%~dp0"

echo ======================================================================
echo       Altium DbLib Manager - Standalone Single-File Executable Builder
echo ======================================================================
echo.

REM 1. Verify Python availability
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 goto ERR_NO_PYTHON
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo   Found %PYTHON_VER%

REM 2. Verify PyInstaller availability
echo.
echo [2/5] Checking PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 goto INSTALL_PYINSTALLER
goto PYINSTALLER_READY

:INSTALL_PYINSTALLER
echo   PyInstaller is not installed. Installing now...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto ERR_PYINSTALLER_INSTALL

:PYINSTALLER_READY
for /f "tokens=*" %%i in ('python -m PyInstaller --version') do set PYINSTALLER_VER=%%i
echo   PyInstaller version: %PYINSTALLER_VER%

REM 3. Clean up previous build artifacts
echo.
echo [3/5] Cleaning previous build folders...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM 4. Build Standalone Single-File Executable using build_exe.spec
echo.
echo [4/5] Running PyInstaller build (bundling all DLLs and dependencies into a single .exe)...
python -m PyInstaller --clean build_exe.spec
if errorlevel 1 goto ERR_BUILD_FAILED

REM 5. Post-build cleanup and placement
echo.
echo [5/5] Finalizing standalone executable...
if exist "build" rmdir /s /q "build"

if not exist "dist\AltiumDbLibManager.exe" goto ERR_EXE_NOT_FOUND

echo   Copying AltiumDbLibManager.exe to project root...
copy /y "dist\AltiumDbLibManager.exe" "%~dp0AltiumDbLibManager.exe" >nul

if exist "database.accdb" copy /y "database.accdb" "dist\" >nul
if exist "library.DbLib" copy /y "library.DbLib" "dist\" >nul
if exist "thunder-light.accdb" copy /y "thunder-light.accdb" "dist\" >nul
if exist "thunder-light.DbLib" copy /y "thunder-light.DbLib" "dist\" >nul
if exist "inventree-viewer-settings.json" copy /y "inventree-viewer-settings.json" "dist\" >nul

echo.
echo ======================================================================
echo [SUCCESS] Standalone Single-File Executable built successfully!
echo.
echo Executable Locations:
echo   [1] Main Project Root:
echo       %~dp0AltiumDbLibManager.exe
echo.
echo   [2] Portable Dist Folder:
echo       %~dp0dist\AltiumDbLibManager.exe
echo.
echo ALL dependencies, Qt, Python DLLs and fonts are bundled inside the .exe!
echo ======================================================================
goto DONE

:ERR_NO_PYTHON
echo.
echo [ERROR] Python is not found in PATH!
echo Please install Python 3.10+ and add it to your PATH environment variable.
goto PAUSE_EXIT

:ERR_PYINSTALLER_INSTALL
echo.
echo [ERROR] Failed to install PyInstaller via pip.
goto PAUSE_EXIT

:ERR_BUILD_FAILED
echo.
echo ======================================================================
echo [ERROR] PyInstaller encountered an error during build!
echo Please check the output above for details.
echo ======================================================================
goto PAUSE_EXIT

:ERR_EXE_NOT_FOUND
echo.
echo [ERROR] Expected executable was not found in dist\AltiumDbLibManager.exe!
goto PAUSE_EXIT

:PAUSE_EXIT
if /i "%~1" neq "--no-pause" (
    echo.
    echo Press any key to exit...
    pause >nul
)
exit /b 1

:DONE
if /i "%~1" neq "--no-pause" (
    echo.
    echo Press any key to exit...
    pause >nul
)
exit /b 0
