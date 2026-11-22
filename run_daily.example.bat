@echo off
:: Daily portfolio batch. Copy this file to run_daily.bat, replace <PROJECT_DIR>
:: below, then schedule run_daily.bat in Windows Task Scheduler.

:: Use this project's virtualenv even if another is active in the shell.
:: Without it pipenv silently reuses the active venv and the run fails with
:: ModuleNotFoundError.
set PIPENV_IGNORE_VIRTUALENVS=1

cd /d "<PROJECT_DIR>"
if not exist logs mkdir logs

:: Keep the log bounded: rotate at 10 MB, one previous archive.
for %%F in (logs\daily_log.txt) do if %%~zF GTR 10485760 (
    move /Y logs\daily_log.txt logs\daily_log_prev.txt >nul
    echo daily_log.txt rotated > logs\daily_log.txt
)

echo ------------------------------------------------ >> logs\daily_log.txt
echo Started %date% %time% >> logs\daily_log.txt

:: Fetch from broker, clean, store. The only writer to the database.
pipenv run python main.py >> logs\daily_log.txt 2>&1

:: Rebuild the Power BI CSVs from the updated database.
pipenv run python -m source.export_powerbi --no-enrich >> logs\daily_log.txt 2>&1

echo Finished %date% %time% >> logs\daily_log.txt
