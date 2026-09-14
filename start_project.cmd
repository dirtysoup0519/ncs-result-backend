@echo off
setlocal

set "BACKEND_DIR=%~dp0"
set "FRONTEND_DIR=%~dp0..\ncs-dashboard\ncs-dashboard"
set "NCS_DATABASE_URL=mysql+pymysql://ncs_ads_reader:zxcvb123W_@192.168.176.100:3306/ncs_analytics"
set "NCS_QUERY_HOST=127.0.0.1"
set "NCS_QUERY_PORT=5000"
set "NCS_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173"

if not exist "%BACKEND_DIR%scripts\run_query.py" (
  echo [ERROR] Backend entry point was not found: %BACKEND_DIR%scripts\run_query.py
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Frontend package was not found: %FRONTEND_DIR%
  echo Set FRONTEND_DIR in start_project.cmd if the frontend was moved.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH.
  pause
  exit /b 1
)

netstat -ano | findstr /R /C:":5000 .*LISTENING" >nul
if errorlevel 1 (
  echo [START] Flask query API: http://127.0.0.1:5000
  start "NCS Query API" /D "%BACKEND_DIR%" cmd /k python scripts\run_query.py
) else (
  echo [SKIP] Port 5000 is already in use. Existing API process is kept.
)

netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul
if errorlevel 1 (
  echo [START] Vue dashboard: http://localhost:5173
  start "NCS Dashboard" /D "%FRONTEND_DIR%" cmd /k npm run dev
) else (
  echo [SKIP] Port 5173 is already in use. Existing frontend process is kept.
)

powershell.exe -NoProfile -Command "Start-Sleep -Seconds 3"
start "" "http://localhost:5173/"
exit /b 0
