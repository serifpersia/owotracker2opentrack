@echo off

:: Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not installed. Please install Python and try again.
    exit /b 1
)

:: Create a virtual environment
python -m venv venv

:: Activate the virtual environment
call venv\Scripts\activate

:: Upgrade pip
pip install --upgrade pip

:: Install the required packages
pip install -r requirements.txt

echo Installation complete. To run the script, use owotracker2opentrack.bat
