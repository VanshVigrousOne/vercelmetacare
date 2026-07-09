@echo off
echo ==========================================
echo           Starting MetaCare
echo ==========================================

:: Check if virtual environment exists
if not exist .venv\Scripts\activate.bat (
    echo [ERROR] Virtual environment .venv not found.
    echo Please run setup.bat first to set up the project.
    pause
    exit /b 1
)

:: Run both backend and frontend in parallel with activated venv
echo [INFO] Starting FastAPI Backend on http://localhost:8000...
start "MetaCare Backend" cmd /c "call .venv\Scripts\activate.bat && uvicorn main:app --reload --port 8000"

echo [INFO] Starting Frontend Server on http://localhost:5500...
start "MetaCare Frontend" cmd /c "call .venv\Scripts\activate.bat && python -m http.server 5500"

echo ==========================================
echo MetaCare is running!
echo Backend:  http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo Frontend: http://localhost:5500
echo ==========================================
pause
