@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No existe .venv. Ejecuta install.bat primero.
  exit /b 1
)
".venv\Scripts\python.exe" src\dictation_app.py
