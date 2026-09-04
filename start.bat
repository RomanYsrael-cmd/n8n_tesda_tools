@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul || (echo Docker Desktop is required. Install it, start it, then try again.& pause & exit /b 1)
docker info >nul 2>nul || (echo Docker Desktop is not running. Start it, wait until ready, then try again.& pause & exit /b 1)
if not exist .env (
  if exist module_builder\.env (
    copy module_builder\.env .env >nul
    echo Existing local settings were moved to the repository launcher.
  ) else if exist .env.example (
    copy .env.example .env >nul
  )
)
docker compose up -d --build
if errorlevel 1 (echo Startup failed. Run "docker compose logs" for details.& pause & exit /b 1)
echo.
echo TESDA Academic Tools is starting at http://localhost:8080
start "" http://localhost:8080
pause
