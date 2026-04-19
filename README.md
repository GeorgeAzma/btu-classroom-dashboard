![BTU Dashboard](btu.png)

# BTU Classroom Dashboard
Personal dashboard for BTU Classroom. Shows courses, grades, materials, calendar, exams.

## Manual Setup
1. open terminal in your chosen folder and copy-paste these commands
``` bash
git clone https://github.com/GeorgeAzma/btu-classroom-dashboard
cd btu-classroom-dashboard
python3 -m venv .venv # make sure python is installed first
pip install -r requirements.txt
python3 main.py
```
2. Sign In and enjoy

## Easy Setup
1. open command prompt and paste
``` bash
curl -sSL -o run.bat "https://raw.githubusercontent.com/GeorgeAzma/btu-classroom-dashboard/main/run.bat" && run.bat
```
#### Linux
``` bash
curl -sSL https://raw.githubusercontent.com/GeorgeAzma/btu-classroom-dashboard/main/run.sh | bash
```

### Notes
- Grades are updated every rerun
- Stop the script by pressing `Ctrl + C` inside terminal
- If you have a problem open Issue on GitHub, or comment on the post
- It is safe to run and passwords are not stored
- You may need to install Git, You can do this using Command Prompt: `winget install Git.Git`
- For headless login, put `BTU_EMAIL` and `BTU_PASSWORD` in a local `.env` file; if they are missing, the script will prompt in the terminal
- Use `--save` to save entered email/password to `.env`