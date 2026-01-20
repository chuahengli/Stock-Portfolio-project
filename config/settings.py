import os
from pathlib import Path
import dotenv
from datetime import datetime

# Load environment variables from .env file
dotenv.load_dotenv()

START_DATE = datetime.strptime(os.getenv("START_DATE", "2024-01-01"), "%Y-%m-%d")

# root directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Define a 'db' directory 
DB_DIR = BASE_DIR / 'db'

# Ensure the db directory exists. Create it if it doesn't
DB_DIR.mkdir(parents=True, exist_ok=True)

MOOMOO_PORTFOLIO_DB_NAME = "moomoo_portfolio.db"
# Full path to your moomoo portfolio database file
MOOMOO_PORTFOLIO_DB_PATH = DB_DIR / MOOMOO_PORTFOLIO_DB_NAME

# --- OpenD Configuration ---
OPEND_DIR = BASE_DIR / "moomoo_OpenD_9.6.5618_Windows"
OPEND_PATH = OPEND_DIR / "OpenD.exe"