@echo off
echo Starting FastAPI server...
uvicorn main:app --reload

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start the server.
    pause
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] Server stopped or exited cleanly.
pause
