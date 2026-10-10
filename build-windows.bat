@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No existe .venv. Ejecuta install.bat primero.
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-windows.lock
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" packaging\build_windows.py
exit /b %errorlevel%
