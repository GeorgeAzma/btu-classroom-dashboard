
#!/bin/bash

REPO_URL="https://github.com/GeorgeAzma/btu-classroom-dashboard"
REPO_NAME="btu-classroom-dashboard"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python is not installed. Installing Python..."
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3 python3-venv python3-pip
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3 python3-pip
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm python python-pip
    elif command -v brew &> /dev/null; then
        brew install python3
    else
        echo "Could not detect package manager. Please install Python manually."
        exit 1
    fi
    echo "Python installed successfully!"
fi

# This script is a raw remote file (not in repo, no main.py, no .git)
if [ ! -f "main.py" ] && [ ! -d ".git" ]; then
    echo "Cloning repo..."
    git clone "$REPO_URL"
    cd "$REPO_NAME" || exit 1
    if [ -f "run.sh" ]; then
        exec bash run.sh
    else
        echo "run.sh not found in repo. Exiting."
        exit 1
    fi
fi


# In repo folder (main.py exists)
if [ -f "main.py" ]; then
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -r requirements.txt
    echo "Checking playwright browser..."
    python3 -m playwright install chromium
    python3 main.py
    exit $?
fi

echo "Could not determine how to run. Exiting."
exit 1
