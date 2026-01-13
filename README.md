# Moomoo Portfolio Tracker & Analyzer

A Python-based automated tool that interfaces with the Moomoo (Futu) OpenD gateway to fetch, clean, and store portfolio data into a local SQLite database. This project is designed to track daily Net Asset Value (NAV), positions, cash flow, and historical orders to facilitate Time-Weighted Return (TWR) performance analysis.

## 🚀 Features

-   **Automated Data Fetching**: Connects to Moomoo OpenD to retrieve real-time account details, positions, and cash flow.
-   **Process Management**: Automatically starts a headless OpenD instance if not running and shuts it down after data retrieval.
-   **Data Cleaning**: Processes raw API data into clean, readable formats (handling currency conversion, rounding, and asset categorization).
-   **Local Database**: Stores all data in a structured SQLite database (`moomoo_portfolio.db`) for privacy and historical analysis.
-   **Performance Metrics**: Calculates NAV and Units to track portfolio performance adjusted for deposits and withdrawals (Time-Weighted Returns).

## 🛠️ Prerequisites

Before running this project, you need the following:

1.  **Python 3.10+**
2.  **Moomoo Account** (Futu Securities)
3.  **Moomoo OpenD Gateway**: This is the bridge software provided by Moomoo to allow API connections.

## ⚙️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name
```

### 2. Install Dependencies
This project uses `pipenv` for dependency management.
```bash
pipenv install
```
*Alternatively, if you use pip:*
```bash
pip install pandas moomoo-api python-dotenv psutil yfinance
```

### 3. External Components (Not included in Repo)

Because this is a public repository, certain proprietary files and sensitive data are excluded via `.gitignore`. You must set these up manually:

#### A. Moomoo OpenD
The API requires the OpenD gateway software to be running.
1.  Download **Moomoo OpenD** from the Futu Open API website.
2.  Extract the folder into the project root directory.
3.  **Important**: Ensure the folder name matches the path defined in `config/settings.py` (e.g., `moomoo_OpenD_9.6.5618_Windows`) or update `settings.py` to match your folder name.

#### B. OpenD Configuration (`OpenD.xml`)
Inside your OpenD folder, configure the `OpenD.xml` file:
1.  Set `<login_account>` to your Moomoo ID.
2.  Set `<login_pwd_md5>` or `<login_pwd>` (Encrypted is recommended).
3.  Set `<rsa_private_key>` to the absolute path of your generated private key (see below).

#### C. RSA Key Generation
For security, this project uses RSA encryption (`is_encrypt=True` in `moomoo_api.py`).
1.  Generate a private/public key pair using OpenSSL or Moomoo's tools.
2.  Place the private key on your local machine.
3.  Upload the public key to your Moomoo Open API settings in the app.

### 4. Environment Variables
Create a `.env` file in the project root to store sensitive paths.

**File: `.env`**
```env
# Absolute path to your RSA private key file
KEY_PATH=C:\Users\YourUser\.ssh\moomoo_api_private_key.txt
```

## 🏃 Usage

To run the daily snapshot:

```bash
python main.py
```

**What happens when you run it:**
1.  Checks if `OpenD.exe` is running; if not, it starts a new headless instance.
2.  Connects to the API and fetches Account Info, Positions, and Cash Flow.
3.  Cleans the data (renames columns, converts currencies to SGD).
4.  Inserts data into `db/moomoo_portfolio.db`.
5.  Calculates the new NAV based on the previous day's units and today's net cash flow.
6.  Terminates the OpenD process (if it was started by the script).

## 🗄️ Database Schema

The project uses SQLite. The database file is located at `db/moomoo_portfolio.db` (created automatically on first run).

-   **`portfolio_snapshots`**: Daily summary of Total Assets, Cash, Market Value, NAV, and Units.
-   **`positions`**: Detailed breakdown of every stock/option held on a specific date.
-   **`cashflow`**: Record of deposits, withdrawals, and dividends.
-   **`historical_orders`**: Log of executed trades.

## ⚠️ Disclaimer

This project is for educational and personal tracking purposes only. It is not financial advice.

-   **Security**: Always keep your private keys and passwords secure. Never commit `OpenD.xml` or `.env` files to version control.
-   **Data Accuracy**: While the tool fetches data from the official API, always verify critical financial data within the official Moomoo app.

## 📂 Project Structure

```text
.
├── config/
│   └── settings.py       # Paths and configuration constants
├── db/                   # Database storage (Ignored by Git)
├── source/
│   ├── cleanup.py        # Data transformation and cleaning logic
│   ├── db.py             # SQLite database interactions
│   └── moomoo_api.py     # Moomoo OpenD API interface
├── main.py               # Entry point
├── Pipfile               # Dependency definitions
└── README.md             # Documentation
```
