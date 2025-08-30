@echo off
echo RICA - Windows Launcher
echo ====================================

REM Check if Poetry is installed
poetry --version >nul 2>&1
if errorlevel 1 (
    echo Error: Poetry is not installed or not in PATH
    echo Please install Poetry first: pip install poetry
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo Warning: .env file not found
    echo Copying from env.example...
    copy "env.example" ".env"
    echo Please edit .env file with your OpenAI API key before running
    pause
)

REM Install dependencies if needed
echo Installing dependencies...
poetry install

REM Run RICA
echo Starting RICA...
echo.
echo Available modes:
echo   - Interactive (default): poetry run rica
echo   - Voice only: poetry run rica --voice
echo   - Text only: poetry run rica --text
echo   - Status: poetry run rica --status
echo   - Test audio: poetry run rica --test-audio
echo.
echo Starting in interactive mode...
poetry run rica

pause
