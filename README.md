# 📈 Moomoo Portfolio Tracker & Analyzer

A tool that interfaces with the **Moomoo OpenD gateway** to store portfolio data into a local SQLite database and display a dashboard using **Streamlit**. This project is designed to automatically track daily portfolio value, positions, cash flow, and historical orders to calculate Time-Weighted Returns.

## ✨ Features

- **Real-time Monitoring:** Dashboard auto-refreshes every 10 seconds
- **Historical Performance:** Tracks daily snapshots of portfolio in database
- **Visualisation:** Plotly-based interactive dashboard for portfolio metrics and allocation
- **OS-keyring credentials:** login, password and RSA key path are stored in Windows Credential Manager / macOS Keychain / Secret Service — never in the repo. `python -m config.credentials setup` to configure, `status` to inspect, `clear` to remove
- **Time-Weighted Return from inception:** TWR anchors to the earliest recorded snapshot (your tracking start date), not a hardcoded value
- **Dividend & Coupon attribution:** cash flows are classified as *external capital* (deposits/withdrawals → adjust NAV units) vs *investment income* (dividends/coupons/taxes → count toward return), so income is no longer mislabelled as capital or silently dropped. Cumulative income is charted on the dashboard
- **Unit tests:** `tests/` covers cash-flow classification and TWR inception logic (`python -m pytest tests/ -q`)
- **Date-stamped realized P/L:** the `net_p_l` table now carries a `date`, so realized P/L snapshots are preserved day-to-day instead of being overwritten; the dashboard shows the latest date
- **Buy/Sell audit ledger:** a `transactions` table (built from `historical_orders` each run) records every fill with multiplier-aware, sign-conventioned `Gross_Amount`; surfaced in a "Trade Ledger" dashboard tab
- **Bounded daily log:** `main.py` logs concise summaries instead of full dataframes, and `run_daily.bat` auto-rotates `logs/daily_log.txt` (keeps one previous archive) when it exceeds 10 MB

## 🛠️ Prerequisites

1. **Python 3.10+**
2. **Moomoo account** with OpenAPI access enabled
3. **RSA key pair** — generated via [Moomoo's Protocol Encryption Process](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html#1479)

## 🚀 Installation & Setup

### 1. Clone and install

```bash
git clone https://github.com/chuahengli/Stock-Portfolio-project.git
cd Stock-Portfolio-project
pip install pipenv
pipenv install
```

### 2. Store your credentials in the OS keyring

Credentials are **never written into this repository**. They go into your operating
system's encrypted credential store — Windows Credential Manager, macOS Keychain, or
Linux Secret Service.

```bash
pipenv run python -m config.credentials setup
```

You will be prompted for three values (the password is typed hidden and never echoed):

| Prompt | Value |
| --- | --- |
| moomoo login | your account ID, email, or phone number |
| moomoo login password | your password (stored encrypted) |
| path to your RSA private key file | e.g. `C:\Users\YourName\.ssh\moomoo_api_private_key.txt` |

Check what is stored — this prints *where* each value came from, never the value:

```bash
pipenv run python -m config.credentials status
```

Remove them again with `pipenv run python -m config.credentials clear`.

> **Why not a `.env` password?** A plaintext password in a file gets screenshotted,
> synced to cloud backups, and pasted into bug reports. The keyring is encrypted at
> rest and unlocked by your OS login. `.env` is used only for non-secret settings.

<details>
<summary><b>Headless / Docker / CI (no OS keyring)</b></summary>

On a server, container, or CI runner there is no Secret Service daemon, so the
keyring is unavailable. Set environment variables instead — `get_secret()` falls back
to them automatically:

```bash
cp .env.example .env
# then set MOOMOO_LOGIN_ACCOUNT / MOOMOO_LOGIN_PWD / MOOMOO_RSA_KEY
```
</details>

### 3. Point the project at OpenD

Install the moomoo **OpenD** gateway (a Windows binary that holds the broker session
and exposes a local API on `127.0.0.1:11111`). Keep it outside the checkout:

```
C:\Users\<you>\.ssh\moomoo_OpenD_9.6.5618_Windows\
```

Then add the two non-secret settings to `.env`:

```bash
cp .env.example .env
```

```bash
# Folder containing OpenD.exe (a path, not a secret)
OPEND_DIR=C:\Users\YourName\.ssh\moomoo_OpenD_9.6.5618_Windows

# Date tracking began (YYYY-MM-DD) -- the history backfill floor
START_DATE="YYYY-MM-DD"
```

You do **not** create `OpenD.xml` yourself. `OpenD.example.xml` (committed, no secrets)
is the 87-line config template; at runtime `config/credentials.py` substitutes your
three keyring values into it and writes `OpenD.xml` next to `OpenD.exe`. That generated
file **does** contain the password, which is why it is gitignored and kept outside the
repo.

### 4. First run

```bash
pipenv run python main.py      # fetch history -> clean -> store in SQLite
pipenv run streamlit run streamlit_app.py
```

The dashboard is **read-only**: it renders whatever `main.py` last wrote. Use the
sidebar **Refresh from broker** button (or `run_daily.bat`) to pull new data — it runs
`main.py` as a separate process so there is exactly one writer.

#### Automated daily run

Copy `run_daily.example.bat` to `run_daily.bat`, replace `<PROJECT_DIR>` with your
checkout path, and register it in Windows Task Scheduler.

## 📂 Project Structure

```text
.
├── config/
│   ├── __init__.py           # (empty)
│   ├── settings.py           # Paths + non-secret settings (no credentials)
│   └── credentials.py        # OS-keyring secret storage + OpenD.xml generation
├── source/
│   ├── cleanup.py            # Data transformation and cleaning logic
│   ├── db.py                 # SQLite database interactions
│   ├── moomoo_api.py         # Moomoo OpenD API interface
│   ├── dashboard.py          # Plotly/pandas visualization logic
│   └── export_powerbi.py     # Exports the DB into the star-schema CSVs
├── tests/                    # Unit tests (pytest) — pure logic, no DB/network
├── db/                       # SQLite database (gitignored — personal data)
├── logs/                     # Daily run logs, auto-rotated (gitignored)
├── main.py                   # Entry point — fetch API data → clean → store to DB
├── streamlit_app.py          # Streamlit UI (READ-ONLY — never writes to the DB)
├── run_daily.example.bat     # Template for the scheduled daily batch
├── OpenD.example.xml         # Config template (no secrets) → generates OpenD.xml
├── Pipfile                   # Dependency definitions (pipenv)
├── .env.example              # Template for non-secret local settings
├── AGENTS.md                 # Repo conventions for AI agents
├── LICENSE
├── .gitignore                # Keeps secrets, DB, logs and binaries out of git
├── powerbi/
│   ├── export/               # 8 star-schema CSVs generated from the DB (Power BI source)
│   ├── POWERBI_ROADMAP.md    # Power BI learning track — course contract + archive
│   └── PowerBI/              # PBIP report + semantic model, NOTES.md journal, Media/
└── README.md
```

## 📊 Power BI Reporting

A full Power BI report built on the same data — a star-schema semantic model loaded from 8
generated CSVs (`powerbi/export/`), written as a **PBIP project** (model + report definition
committed in this repo, no opaque .pbix). Refresh is a folder connector over the export
directory: re-run `pipenv run python -m source.export_powerbi --no-enrich` and hit Refresh.

**3 report pages (1280×720):**

| Page | Contents |
| ---- | -------- |
| Overview | Assets, cash/stocks/options allocation, portfolio vs benchmark growth, sector & country allocation |
| Risks | Volatility, max drawdown, Beta vs S&P 500, Sortino, Sharpe, Historical VaR (95%), Expected Shortfall (95%), Calmar, Tracking Error, Information Ratio, correlation heatmap, daily-return histogram, symbol allocation treemap |
| Trades | Full buy/sell ledger + net trade cash-flow matrix, filterable by period |

**30 DAX measures**, every one QA'd against Python recomputation from the raw CSVs
(e.g. Historical VaR 95% = −5.57%, Expected Shortfall = −7.78%, worst single day on record
−15.5%). Period slicing is a disconnected-table window system (1W / 1M / 3M / 6M / YTD / ALL)
applied inside each measure. The learning track and measure designs are documented in
[`powerbi/POWERBI_ROADMAP.md`](powerbi/POWERBI_ROADMAP.md) with a user-written journal in
[`powerbi/PowerBI/NOTES.md`](powerbi/PowerBI/NOTES.md).

| Overview page | Risks page |
| ------------- | ---------- |
| ![Overview page](powerbi/PowerBI/Media/Checkpoint%203%20-%20Page%201.png) | ![Risks page](powerbi/PowerBI/Media/Checkpoint%204%20-%20Page%202.png) |

> Screenshots are redacted for privacy — portfolio values, holdings and trade details are hidden; the full-res interactive report is not published.

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