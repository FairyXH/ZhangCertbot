@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] 未找到 Python，请安装 Python 3.10 或更高版本并加入 PATH。
    exit /b 1
)

echo [1/3] 检查 PyInstaller...
python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] 正在安装 PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

echo [2/3] 构建单文件 GUI...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ZhangCertbot ^
    --paths "%CD%" ^
    --collect-all paramiko ^
    gui.py
if errorlevel 1 (
    echo [ERROR] 打包失败。
    exit /b 1
)

echo [3/3] 构建完成：%CD%\dist\ZhangCertbot.exe
echo 首次运行前，请将 data 配置目录放在 exe 同级目录，并确保 Certbot 可用。
endlocal