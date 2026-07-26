import os
from pathlib import Path
import dotenv
from datetime import datetime

# Load local .env first (project-level settings like START_DATE)
dotenv.load_dotenv()

# Load secure credentials from a .env file stored outside the project tree.
# Override with MOOMOO_SECRET_ENV env var (set in your project-level .env),
# or it defaults to a convention path.
# Inside a Docker sandbox, the path won't exist — safe silent no-op.
_SECRET_ENV_PATH = os.getenv(
    "MOOMOO_SECRET_ENV",
    "C:/Users/<you>/.ssh/moomoo_creds.env",
)
_SECRET_ENV = Path(_SECRET_ENV_PATH)
if _SECRET_ENV.exists():
    dotenv.load_dotenv(_SECRET_ENV, override=True)

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
# Read OPEND_DIR from env var (set in the secure .env), fallback to old path
OPEND_DIR = Path(os.getenv("OPEND_DIR", str(BASE_DIR / "moomoo_OpenD_9.6.5618_Windows")))
OPEND_PATH = OPEND_DIR / "OpenD.exe"
OPEND_XML_PATH = OPEND_DIR / "OpenD.xml"
OPEND_XML_TEMPLATE = OPEND_DIR / "OpenD.example.xml"