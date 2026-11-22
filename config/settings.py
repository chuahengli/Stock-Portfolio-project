"""Project configuration: paths and non-secret settings.

What lives here: paths, date ranges, the DB location. Anything a reviewer could
read in a diff without harm.

What does NOT live here: credentials. Secrets are resolved by
``config.credentials.get_secret`` from the OS keyring, falling back to
environment variables for headless runs. Set them up once with:

    python -m config.credentials setup

The previous design loaded a SECOND .env from outside the project tree
(``C:/Users/<you>/.ssh/moomoo_creds.env``) to keep the password away from a
Docker-mounted workspace. That threat model no longer applies now the pipeline
runs on the host, and the hardcoded literal ``<you>`` never resolved for anyone
else -- so the indirection is gone.
"""
import os
from pathlib import Path

import dotenv
from datetime import datetime

# Project-level settings only (START_DATE, OPEND_DIR). Not secrets.
dotenv.load_dotenv()

# root directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

START_DATE = datetime.strptime(os.getenv("START_DATE", "2024-01-01"), "%Y-%m-%d")

# Define a 'db' directory
DB_DIR = BASE_DIR / "db"

# Ensure the db directory exists. Create it if it doesn't
DB_DIR.mkdir(parents=True, exist_ok=True)

MOOMOO_PORTFOLIO_DB_NAME = "moomoo_portfolio.db"
# Full path to your moomoo portfolio database file
MOOMOO_PORTFOLIO_DB_PATH = DB_DIR / MOOMOO_PORTFOLIO_DB_NAME

# --- OpenD Configuration ---
# OPEND_DIR is a PATH, not a secret: set it in .env if your OpenD install is
# somewhere unusual. This default matches the documented location.
OPEND_DIR = Path(os.getenv("OPEND_DIR", str(BASE_DIR / "moomoo_OpenD_9.6.5618_Windows")))
OPEND_PATH = OPEND_DIR / "OpenD.exe"
OPEND_XML_PATH = OPEND_DIR / "OpenD.xml"
OPEND_XML_TEMPLATE = OPEND_DIR / "OpenD.example.xml"

# --- Logs ---
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DAILY_LOG_PATH = LOG_DIR / "daily_log.txt"
