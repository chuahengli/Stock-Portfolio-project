@echo off
:: TEMPLATE for the daily portfolio batch. The real run_daily.bat is
:: machine-local (gitignored) -- copy this file, fill in <PROJECT_DIR>,
:: and register it in Windows Task Scheduler.
:: PIPENV_IGNORE_VIRTUALENVS=1 forces pipenv to use THIS project's own
:: virtualenv even when another venv happens to be active in the shell.
set PIPENV_IGNORE_VIRTUALENVS=1
cd /d "<PROJECT_DIR>"

:: Rotate the log if it grows too large (bounded; keep the one previous archive)
for %%F in (daily_log.txt) do if %%~zF GTR 10485760 (
    move /Y daily_log.txt daily_log_prev.txt >nul
    echo daily_log.txt rotated > daily_log.txt
)

:: Log the start time
echo ------------------------------------------------ >> daily_log.txt
echo Script started at %date% %time% >> daily_log.txt

:: Run the script using pipenv and redirect output/errors to the log file
pipenv run python main.py >> daily_log.txt 2>&1
:: Export clean CSV star-schema for Power BI (fast, offline-safe)
pipenv run python -m source.export_powerbi --no-enrich >> daily_log.txt 2>&1

:: Log the end time
echo Script finished at %date% %time% >> daily_log.txt
