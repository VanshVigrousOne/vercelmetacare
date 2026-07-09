@echo off
echo ==========================================
echo           MetaCare Setup Script
echo ==========================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python.
    pause
    exit /b 1
)

:: Create virtual environment
if not exist .venv (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
) else (
    echo [INFO] Virtual environment .venv already exists.
)

:: Install dependencies
echo [INFO] Installing/Updating dependencies...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

:: Fix corrupted .env from previous runs if any
if exist .env (
    findstr /C:"=%%A" .env >nul && del .env
    findstr /C:"=%%a" .env >nul && del .env
    findstr /C:"=%%A" .env >nul || findstr /C:"=%%a" .env >nul || findstr /C:"=%%" .env >nul && del .env
)
:: Also check if .env has "%A"
if exist .env (
    findstr /C:"=%A" .env >nul && del .env
    findstr /C:"=%a" .env >nul && del .env
    findstr /C:"=%" .env >nul && del .env
)

:: Generate .env if not exists
if not exist .env (
    echo [INFO] Generating .env configuration file...
    for /f "tokens=*" %%A in ('python -c "import secrets; print(secrets.token_hex(32))"') do (
        echo JWT_SECRET_KEY=%%A> .env
    )
    echo GEMINI_API_KEY=your-gemini-api-key-here>> .env
    echo [INFO] .env file created with a generated JWT_SECRET_KEY.
    echo [IMPORTANT] Please open .env and add your actual GEMINI_API_KEY.
) else (
    echo [INFO] .env already exists. Skipping creation.
)

:: Seed database
echo [INFO] Seeding the database with demo credentials...
.venv\Scripts\python seed.py

echo ==========================================
echo Setup completed successfully!
echo You can now start the application by running run.bat
echo ==========================================
pause
