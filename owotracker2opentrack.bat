@echo off
setlocal

goto run_leap

:run_leap
call venv\Scripts\activate
python owotracker2opentrack.py
deactivate
goto end

:end
endlocal
