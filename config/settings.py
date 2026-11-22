"""Paths and non-secret settings.

Credentials are NOT here -- they live in the OS keyring. See config/credentials.py.

    python -m config.credentials setup
"""
import os
from pathlib import Path

import dotenv
from datetime import datetime

# Loads START_DATE and OPEND_DIR. No secrets in that file.
dotenv.load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

START_DATE = datetime.strptime(os.getenv("START_DATE", "2024-01-01"), "%Y-%m-%d")

DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

MOOMOO_PORTFOLIO_DB_NAME = "moomoo_portfolio.db"
MOOMOO_PORTFOLIO_DB_PATH = DB_DIR / MOOMOO_PORTFOLIO_DB_NAME

# OpenD gateway locations. OPEND_DIR is a path, not a secret.
OPEND_DIR = Path(os.getenv("OPEND_DIR", str(BASE_DIR / "moomoo_OpenD_9.6.5618_Windows")))
OPEND_PATH = OPEND_DIR / "OpenD.exe"
OPEND_XML_PATH = OPEND_DIR / "OpenD.xml"
OPEND_XML_TEMPLATE = OPEND_DIR / "OpenD.example.xml"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DAILY_LOG_PATH = LOG_DIR / "daily_log.txt"
