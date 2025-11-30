#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python is not installed. Installing Python..."
    
    # Detect package manager and install Python
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

if [ ! -f "main.py" ]; then
    git clone https://github.com/GeorgeAzma/btu-classroom-dashboard
    cd btu-classroom-dashboard || exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
