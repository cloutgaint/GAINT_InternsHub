@echo off
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo ERROR: Start Docker Desktop, wait until it says Engine running, then run this file again.
  pause
  exit /b 1
)

docker compose -p gaint-interns-hub-v8-1 up -d --wait postgres
if errorlevel 1 (
  echo ERROR: PostgreSQL could not start. Check Docker Desktop.
  pause
  exit /b 1
)

if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
if not exist "backend\.venv\Scripts\python.exe" python -m venv backend\.venv

call backend\.venv\Scripts\activate.bat
python -m pip install -r backend\requirements.txt
start "GAINT V8.1 Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload"

cd frontend
call npm install
start "GAINT V8.1 Frontend" cmd /k "npm run dev"
cd ..

echo.
echo GAINT Interns Hub V8.1 is starting.
echo App:      http://localhost:5173
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Use stop-windows.bat when finished.
pause
endlocal
