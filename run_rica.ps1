# RICA - PowerShell Launcher
# ======================================

Write-Host "RICA - PowerShell Launcher" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""

# Check if Poetry is installed
try {
    $poetryVersion = poetry --version
    Write-Host "Poetry found: $poetryVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Poetry is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Poetry first: pip install poetry" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "Warning: .env file not found" -ForegroundColor Yellow
    Write-Host "Copying from env.example..." -ForegroundColor Yellow
    
    if (Test-Path "env.example") {
        Copy-Item "env.example" ".env"
        Write-Host "Please edit .env file with your OpenAI API key before running" -ForegroundColor Yellow
        Write-Host "You can use: notepad .env" -ForegroundColor Cyan
        Read-Host "Press Enter after editing the .env file"
    } else {
        Write-Host "Error: env.example file not found" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Install dependencies if needed
Write-Host "Installing dependencies..." -ForegroundColor Cyan
poetry install

# Show available modes
Write-Host ""
Write-Host "Available modes:" -ForegroundColor Cyan
Write-Host "  - Interactive (default): poetry run rica" -ForegroundColor White
Write-Host "  - Voice only: poetry run rica --voice" -ForegroundColor White
Write-Host "  - Text only: poetry run rica --text" -ForegroundColor White
Write-Host "  - Status: poetry run rica --status" -ForegroundColor White
Write-Host "  - Test audio: poetry run rica --test-audio" -ForegroundColor White
Write-Host ""

# Ask user for mode
Write-Host "Select mode:" -ForegroundColor Yellow
Write-Host "1. Interactive (default)" -ForegroundColor White
Write-Host "2. Voice only" -ForegroundColor White
Write-Host "3. Text only" -ForegroundColor White
Write-Host "4. Status" -ForegroundColor White
Write-Host "5. Test audio" -ForegroundColor White

$choice = Read-Host "Enter choice (1-5) or press Enter for default"

# Set command based on choice
switch ($choice) {
    "2" { $command = "poetry run rica --voice" }
    "3" { $command = "poetry run rica --text" }
    "4" { $command = "poetry run rica --status" }
    "5" { $command = "poetry run rica --test-audio" }
    default { $command = "poetry run rica" }
}

Write-Host ""
Write-Host "Starting RICA..." -ForegroundColor Green
Write-Host "Command: $command" -ForegroundColor Cyan
Write-Host ""

# Run RICA
Invoke-Expression $command

Write-Host ""
Read-Host "Press Enter to exit"
