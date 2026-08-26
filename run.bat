@echo off
setlocal
cd /d "%~dp0"
if /I "%1"=="gui" (
    python gui.py
) else (
    python main.py %*
)
endlocal
