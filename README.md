# Moomoo Portfolio Tracker

Connects to a moomoo (Futu) brokerage account, saves a daily snapshot of the portfolio
to a local SQLite file, and reports it two ways: a Streamlit dashboard and a Power BI
report.

![Overview page](powerbi/PowerBI/Media/Checkpoint%203%20-%20Page%201.png)

> Screenshot shows allocation percentages and indexed performance only — dollar amounts, holdings and trade details are omitted.

## What it does

| Capability | Detail |
| --- | --- |
| **Daily tracking** | Snapshot of total assets, equity, options and cash, written once per run |
| **Time-weighted return** | NAV/unit unitisation anchored to the first recorded snapshot, so deposits don't flatter performance |
| **Cash-flow classification** | Each flow labelled external capital (deposit/withdrawal), investment income (dividend/coupon/tax), or internal (FX, fund subscription) |
| **Multi-currency** | Positions in USD and SGD, converted to one base currency for reporting |
| **Trade ledger** | Every fill recorded with sign convention and the options ×100 multiplier applied |
| **Options aware** | OCC-style contract symbols parsed for underlying, expiry and strike |
| **Streamlit dashboard** | Four tabs: **Overview** (asset trend, return vs benchmark, sector/country/market-cap breakdown, dividend income), **Positions** (live holdings with P/L), **P/L Analysis** (net P/L by market, stock vs option), **Trade Ledger** (every fill) |
| **Power BI report** | Three pages: **Overview** (allocation, portfolio vs benchmark growth), **Risks** (volatility, drawdown, Beta, Sharpe, Sortino, VaR, Expected Shortfall, correlation heatmap), **Trades** (ledger and cash-flow matrix), all period-filterable |

## Architecture

```
moomoo OpenD gateway
        │
        ▼
     main.py
        │
        ▼
  db/moomoo_portfolio.db  (SQLite)
        │
   ┌────┴────┐
   ▼         ▼
streamlit  export_powerbi.py → powerbi/export/*.csv → Power BI
```

## Setup

**Prerequisites:**
- **Python 3.12** (`Pipfile`)
- **moomoo account with OpenAPI access** (defaults to Moomoo SG / SGD in `source/moomoo_api.py` via `security_firm="FUTUSG"`, `currency="SGD"`)
- **1024-bit PKCS#1 RSA private key** (no passphrase), generated via [moomoo's protocol encryption guide](https://openapi.moomoo.com/moomoo-api-doc/en/qa/other.html)

### 1. Install dependencies

```bash
git clone https://github.com/chuahengli/Stock-Portfolio-project.git
cd Stock-Portfolio-project
pip install pipenv
pipenv install --dev
```

### 2. Download the OpenD gateway

Download OpenD from **[moomoo.com/download/OpenAPI](https://www.moomoo.com/download/OpenAPI)**
(version ≥ 10.11 to match the locked `moomoo-api` SDK) and extract it outside the repo
(for example `C:\Users\YourName\.ssh\moomoo_OpenD_Windows`).

### 3. Store credentials in the OS keyring

Credentials are stored in your OS credential store (Windows Credential Manager, macOS
Keychain, or Linux Secret Service) — never in the repository:

```bash
pipenv run python -m config.credentials setup
```

Enter your **moomoo login** (ID/email/phone), **password** (input is hidden), and **RSA
private key path**. Check or clear stored entries anytime with:

```bash
pipenv run python -m config.credentials status
pipenv run python -m config.credentials clear
```

<details>
<summary><b>Headless / CI fallback (no OS keyring)</b></summary>

Set `MOOMOO_LOGIN_ACCOUNT`, `MOOMOO_LOGIN_PWD`, and `MOOMOO_RSA_KEY` in `.env`.
`get_secret()` falls back to environment variables only when no keyring entry exists.
</details>

### 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` — set your tracking start date and uncomment `OPEND_DIR` to point at your
extracted OpenD folder from step 2:

```bash
START_DATE="2024-01-01"
OPEND_DIR=C:\Users\YourName\.ssh\moomoo_OpenD_Windows
```

> On a new machine, launch `OpenD.exe` once manually to accept the initial agreement or SMS device verification, then close it. `main.py` generates `OpenD.xml` from your keyring credentials and manages OpenD after that.

### 5. First run (backfill database)

```bash
pipenv run python main.py
```

This creates `db/moomoo_portfolio.db`, backfills cash flows since `START_DATE`
(rate-limited by moomoo to 20 days per 30 seconds — a multi-year backfill takes ~15–30
minutes), and records today's snapshot:

```
Update Complete. New NAV: 25.0000, Net CF: 0.00, New Units: 1000.0000
Database updated successfully.
```

### 6. Open the dashboard (or Power BI report)

```bash
pipenv run streamlit run streamlit_app.py
```

**Live Mode** (top toggle, on by default) refreshes the display every 10 seconds
from the database. The nightly batch (`main.py`) is the only writer of record.
Toggle it off to stop polling. The dark theme is set in `.streamlit/config.toml`.

**Stopping the app:** press Ctrl+C. Streamlit closes, and the OpenD gateway this
app launched is shut down with it. A gateway you started manually is left running.
If one is ever orphaned, kill it with `taskkill /IM OpenD.exe /F`.

**Optional — Power BI report:**
1. Export the 8 star-schema CSVs: `pipenv run python -m source.export_powerbi`
2. Open `powerbi/PowerBI/Stock Portfolio PowerBI.pbip` in Power BI Desktop.
3. In **Transform data → Data source settings**, repoint the CSV folder to your local
   `powerbi/export/` directory and click **Refresh**.

## Running after that

Later runs fetch the last 30 days (extended if the machine was off longer).
Use either mode independently; neither requires the other to be running:

- **Option A — From the dashboard:** Click **Refresh from broker** in the Streamlit
  sidebar. It runs `main.py` as a subprocess and reloads the page.
- **Option B — Scheduled batch (no dashboard needed):** Copy `run_daily.example.bat` to
  `run_daily.bat`, replace `<PROJECT_DIR>` with your repo path, and schedule it in
  Windows Task Scheduler under your Windows user account. It updates SQLite, refreshes
  `powerbi/export/*.csv`, and logs to `logs/daily_log.txt` (auto-rotated at 10 MB).

## Project structure

```text
.
├── config/
│   ├── settings.py           # Paths and non-secret settings (.env)
│   └── credentials.py        # OS keyring CLI + runtime OpenD.xml generator
├── source/
│   ├── moomoo_api.py         # OpenD process lifecycle and broker queries
│   ├── cleanup.py            # API DataFrame cleaning and cash-flow classification
│   ├── db.py                 # SQLite schema, upserts, NAV/unit TWR, price history
│   ├── dashboard.py          # Plotly figures and table formatting
│   ├── live.py               # 10s moomoo quote poller (live_* tables only)
│   └── export_powerbi.py     # SQLite → 8 star-schema CSVs for Power BI
├── tests/                    # Pure-logic unit tests (pytest)
├── powerbi/
│   ├── PowerBI/              # PBIP report and semantic model (36 DAX measures)
│   ├── POWERBI_ROADMAP.md    # Star-schema export contract and measure notes
│   ├── verify_export.py      # CSV schema and BOM checker
│   └── verify_te_ir.py       # Tracking Error / Information Ratio DAX verifier
├── main.py                   # Batch entry point (sole database writer)
├── streamlit_app.py          # Streamlit dashboard (read-only)
├── OpenD.example.xml         # OpenD configuration template
├── run_daily.example.bat     # Windows Task Scheduler batch template
├── .env.example              # Non-secret settings template
└── Pipfile
```

Generated at runtime (gitignored): `db/`, `logs/`, `powerbi/export/`,
`powerbi/symbol_meta.json`, `OpenD.xml`, `.env`, `run_daily.bat`.

## Data model

| Table | Grain | Role |
| --- | --- | --- |
| `portfolio_snapshots` | one row per run | Source: total assets, stocks, options, cash, NAV, units |
| `positions` | symbol × date | Source: quantity, cost, market value, unrealised P/L |
| `historical_orders` | order | Source: raw fills |
| `cashflow` | cash-flow entry | Source: classified deposits, dividends, taxes |
| `transactions` | order | Derived: sign-conventioned, multiplier-aware ledger |
| `net_p_l` | date × symbol × market × currency | Derived: realised and unrealised P/L |
| `benchmark_history` | date × index | Source: daily closes for 8 benchmark indices |
| `symbol_price_history` | date × symbol | Source: daily closes for every equity ever held |
| `app_meta` | key | Internal: state flags (e.g. `last_symbol_prices_update`) |

`Source` tables store broker and Yahoo Finance history; `Derived` tables are rebuilt on
every run.

## How to run the tests

```bash
pipenv run python -m pytest tests/ -q
```

49 pure-logic tests (~20 seconds, no database, network, or broker account required):
cash-flow classification, TWR unitisation, order handling, option multipliers,
trade-ledger sign conventions, and shutdown cleanup.

## Known limitations

- **Windows-first:** `source/moomoo_api.py` manages `OpenD.exe` by its Windows binary
  name and the scheduled job is a `.bat` script; macOS/Linux requires changing the
  binary name (`OpenD`) and using cron/systemd.
- **Separate gateway binary:** OpenD (~100 MB), an RSA keypair, broker OpenAPI approval,
  and a one-time manual device login are required before automated runs work.
- **Single account, Moomoo SG / SGD base:** `security_firm="FUTUSG"` and SGD conversion
  are the defaults; other regions or base currencies require changing
  `source/moomoo_api.py` and the conversion target.
- **Broker history depth:** Order history may not reach as far back as cash-flow
  history, so early realised P/L can be incomplete.
- **Local file storage:** Single-user SQLite file on disk with no cloud sync or hosting.
