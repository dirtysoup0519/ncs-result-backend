@echo off
setlocal
set "NCS_REPO_ROOT=%~dp0"
set "NCS_PYTHON=%NCS_REPO_ROOT%.venv\Scripts\python.exe"
if not exist "%NCS_PYTHON%" (
  echo [ERROR] Missing project Python environment.
  echo Run start_project.cmd once before exporting data.
  pause
  exit /b 1
)
"%NCS_PYTHON%" "%NCS_REPO_ROOT%scripts\export_dataset.py" %*
if errorlevel 1 pause
exit /b %errorlevel%
