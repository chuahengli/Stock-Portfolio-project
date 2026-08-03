# 📈 Moomoo Portfolio Tracker & Analyzer

A tool that interfaces with the **Moomoo OpenD gateway** to store portfolio data into a local SQLite database and display a dashboard using **Streamlit**. This project is designed to automatically track daily portfolio value, positions, cash flow, and historical orders to calculate Time-Weighted Returns.

## ✨ Features

- **Real-time Monitoring:** Dashboard auto-refreshes every 10 seconds
- **Historical Performance:** Tracks daily snapshots of portfolio in database
- **Visualisation:** Plotly-based interactive dashboard for portfolio metrics and allocation
- **Secure Credential Isolation:** Credentials live outside the project tree — safe for AI-assisted development environments
- **Time-Weighted Return from inception:** TWR anchors to the earliest recorded snapshot (your tracking start date), not a hardcoded value
- **Dividend & Coupon attribution:** cash flows are classified as *external capital* (deposits/withdrawals → adjust NAV units) vs *investment income* (dividends/coupons/taxes → count toward return), so income is no longer mislabelled as capital or silently dropped. Cumulative income is charted on the dashboard
- **Unit tests:** `tests/` covers cash-flow classification and TWR inception logic (`python -m pytest tests/ -q`)
- **Date-stamped realized P/L:** the `net_p_l` table now carries a `date`, so realized P/L snapshots are preserved day-to-day instead of being overwritten; the dashboard shows the latest date
- **Buy/Sell audit ledger:** a `transactions` table (built from `historical_orders` each run) records every fill with multiplier-aware, sign-conventioned `Gross_Amount`; surfaced in a "Trade Ledger" dashboard tab
- **Bounded daily log:** `main.py` now logs concise summaries instead of full dataframes, and `run_daily.bat` auto-rotates `daily_log.txt` (keeps one previous archive) when it exceeds 10 MB

## 🛠️ Prerequisites

Before running this project, you need the following:

1. **Python 3.10+**
2. **Moomoo Account** with OpenD API access
3. **RSA Key Pair** — generated via [Moomoo's Protocol Encryption Process](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html#1479)

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/chuahengli/Stock-Portfolio-project.git
```

### 2. Set Up the Moomoo OpenD Gateway

The moomoo OpenD gateway (`OpenD.exe`) is a Windows binary that logs into your moomoo account and exposes a local API. The OpenD folder is **not** stored in the project directory — it lives in a secure location on your host machine to keep credentials isolated.

1. Move the `moomoo_OpenD_9.6.5618_Windows` folder to:
   ```
   C:\Users\<you>\.ssh\moomoo_OpenD_9.6.5618_Windows\
   ```
2. The `OpenD.example.xml` template at the project root is used by `config/credentials.py` to generate the real `OpenD.xml` at runtime
3. The XML will be populated with your credentials from the `.env` file at runtime

### 3. RSA Key Generation

1. Generate a private/public key pair by following [Moomoo's Protocol Encryption Process](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html#1479)
2. Save the private key to a text file (e.g. `C:\Users\<you>\.ssh\moomoo_api_private_key.txt`)
3. Reference this file path in your `.env` (see below)

### 4. Configure `.env`

1. Rename `.env.example` → `.env`
2. Fill in your credentials:

```bash
# Path to your RSA private key file
MOOMOO_RSA_KEY=C:\Users\YourName\.ssh\moomoo_api_private_key.txt

# Your moomoo login account (user ID, phone number, or email)
MOOMOO_LOGIN_ACCOUNT=YOUR_LOGIN_ACCOUNT_HERE

# Your moomoo login password (plain text — used to generate OpenD.xml at runtime)
MOOMOO_LOGIN_PWD=your_password

# Path to the moomoo_OpenD folder
OPEND_DIR=C:\Users\YourName\.ssh\moomoo_OpenD_9.6.5618_Windows

# Date you opened your Moomoo account (YYYY-MM-DD)
START_DATE="2023-08-07"
```

> **Why this structure?**
> - The `.env` file is in `.gitignore` and never committed
> - The OpenD folder (with `OpenD.xml`) lives outside the project tree
> - At runtime, `config/credentials.py` reads the `.env`, generates the real `OpenD.xml` from the template, then starts OpenD — so credentials never sit in the project directory

### 5. Install Dependencies

This project uses `pipenv` for dependency management:

```bash
pip install pipenv
pipenv install
```

## 📂 Project Structure

```text
.
├── config/
│   ├── __init__.py          # (empty)
│   ├── settings.py           # Paths, configuration constants, env loading
│   └── credentials.py        # Loads secure credentials, generates OpenD.xml
├── db/                       # SQLite database storage (gitignored)
├── source/
│   ├── cleanup.py            # Data transformation and cleaning logic
│   ├── db.py                 # SQLite database interactions
│   ├── moomoo_api.py         # Moomoo OpenD API interface
│   └── dashboard.py          # Plotly/pandas visualization logic
├── main.py                   # Entry point — fetch API data → clean → store to DB
├── streamlit_app.py          # Interactive Streamlit Web UI
├── OpenD.example.xml         # Template to generate credentials-bearing OpenD.xml
├── Pipfile                   # Dependency definitions (pipenv)
├── .env.example              # Template for credential configuration
├── .gitignore                # Prevents leakage of secrets, DB, runtime binaries
└── README.md
```

## 📊 Usage

### Initialize / Update Database

Run the main script to fetch historical cashflow data and today's snapshot:

```bash
pipenv run python main.py
```

On first run this fetches all historical data since `START_DATE`. Subsequent runs update only the last 30 days.

### Launch Dashboard

```bash
pipenv run streamlit run streamlit_app.py
```

The dashboard auto-refreshes every 10 seconds in Live Mode. Toggle it off to freeze the view.