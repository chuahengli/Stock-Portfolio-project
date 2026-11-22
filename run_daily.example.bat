@echo off
:: TEMPLATE for the daily portfolio batch. Copy to run_daily.bat, replace
:: <PROJECT_DIR> with your checkout path, and register it in Task Scheduler.
::
:: PIPENV_IGNORE_VIRTUALENVS=1 forces THIS project's virtualenv even when another
:: venv is active in the shell (pipenv otherwise silently reuses it and the run
:: dies with ModuleNotFoundError).
set PIPENV_IGNORE_VIRTUALENVS=1
cd /d "<PROJECT_DIR>"

if not exist logs mkdir logs

:: Rotate the log when it exceeds 10 MB (bounded; keep one previous archive)
for %%F in (logs\daily_log.txt) do if %%~zF GTR 10485760 (
    move /Y logs\daily_log.txt logs\daily_log_prev.txt >nul
    echo daily_log.txt rotated > logs\daily_log.txt
)

echo ------------------------------------------------ >> logs\daily_log.txt
echo Script started at %date% %time% >> logs\daily_log.txt

:: Fetch from broker -> clean -> store (single writer)
pipenv run python main.py >> logs\daily_log.txt 2>&1
:: Export the star-schema CSVs for Power BI (fast, offline-safe)
pipenv run python -m source.export_powerbi --no-enrich >> logs\daily_log.txt 2>&1

echo Script finished at %date% %time% >> logs\daily_log.txt
