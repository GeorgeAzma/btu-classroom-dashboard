@echo off
setlocal EnableDelayedExpansion

:: Check if Python is installed and accessible
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed. Downloading Python installer...
    
    :: Download Python installer to temp folder
    set "INSTALLER=%TEMP%\python_installer.exe"
    curl -L -o "!INSTALLER!" https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe
    if %errorlevel% neq 0 (
        echo Failed to download Python. Please install manually from https://python.org/downloads
        pause
        exit /b 1
    )
    
    :: Install Python silently with PATH option
    echo Installing Python...
    start /wait "" "!INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    
    :: Cleanup installer
    del "!INSTALLER!" 2>nul
    
    echo.
    echo Python installation completed!
    echo Please close this window and run the script again.
    echo ^(This is needed so Windows can recognize the new Python installation^)
    pause
    exit /b 0
)

:: Clone repository if not already in it
if not exist "main.py" (
    git clone https://github.com/GeorgeAzma/btu-classroom-dashboard
    cd btu-classroom-dashboard
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate virtual environment and install requirements
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

:: Run the application
echo Starting application...
python main.py

pause