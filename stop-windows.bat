@echo off
setlocal
cd /d "%~dp0"
docker compose -p gaint-interns-hub-v8-1 stop postgres
echo PostgreSQL stopped. Close the backend and frontend terminal windows.
pause
endlocal
