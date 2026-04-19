@echo off
setlocal EnableDelayedExpansion

set REPO_URL=https://github.com/GeorgeAzma/btu-classroom-dashboard
set REPO_NAME=btu-classroom-dashboard

:: Check if Python is installed
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed. Downloading Python installer...
    set "INSTALLER=%TEMP%\python_installer.exe"
    curl -L -o "!INSTALLER!" https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe
    if %errorlevel% neq 0 (
        echo Failed to download Python. Please install manually from https://python.org/downloads
        pause
        exit /b 1
    )
    echo Installing Python...
    start /wait "" "!INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del "!INSTALLER!" 2>nul
    echo.
    echo Python installation completed!
    echo Please close this window and run the script again.
    echo ^(This is needed so Windows can recognize the new Python installation^)
    pause
    exit /b 0
)

:: This script is a raw remote file (not in repo, no main.py, no .git)
if not exist "main.py" if not exist ".git" (
    echo Cloning repo...
    git clone %REPO_URL%
    cd %REPO_NAME%
    if exist "run.bat" (
        call run.bat %*
        exit /b %errorlevel%
    ) else (
        echo run.bat not found in repo. Exiting.
        exit /b 1
    )
)


:: In repo folder (main.py exists)
if exist "main.py" (
    set "VENV_CREATED=0"
    if not exist ".venv" (
        echo Creating virtual environment...
        python -m venv .venv
        set "VENV_CREATED=1"
    )
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
    if "%VENV_CREATED%"=="1" (
        echo Installing requirements...
        pip install -r requirements.txt
    )
    python main.py %*
    exit /b %errorlevel%
)

echo Could not determine how to run. Exiting.
exit /b 1

echo Starting application...
python main.py

pause