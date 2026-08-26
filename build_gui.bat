@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required and must be on PATH.
    exit /b 1
)

echo [1/3] Checking PyInstaller...
python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

echo [2/3] Building single-file GUI executable...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ZhangCertbot ^
    --paths "%CD%" ^
    --collect-all paramiko ^
    gui.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

echo [3/3] Build complete: %CD%\dist\ZhangCertbot.exe
echo Put the data directory beside the executable before first use.
endlocal
