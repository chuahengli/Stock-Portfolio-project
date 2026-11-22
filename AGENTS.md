# Stock Portfolio project


## Architecture

- Data pipeline: moomoo OpenD -> cleaning -> main.py -> SQLite (`db/moomoo_portfolio.db`).
- `main.py` is the SINGLE writer. The Streamlit dashboard is read-only.
- Two output layers on the SAME database:
  1. Streamlit dashboard (operational): `streamlit_app.py`
  2. Power BI analysis/reporting: `source/export_powerbi.py` ->
     `powerbi/export/*.csv`, `powerbi/PowerBI` PBIP project files with images

## Credentials

- Secrets live in the OS keyring (Windows Credential Manager / Keychain /
  Secret Service). Resolve them ONLY via `config.credentials.get_secret(field)`.
  Never read `os.getenv` for a secret in new code, and never print a resolved value.
- Setup: `python -m config.credentials setup` | `status` | `clear`
- The env vars (`MOOMOO_LOGIN_ACCOUNT`, `MOOMOO_LOGIN_PWD`, `MOOMOO_RSA_KEY`) are
  the headless/CI fallback only.
- `.env` holds NON-SECRET config only (`START_DATE`, `OPEND_DIR`).
- `OpenD.example.xml` is committed (template, placeholders only). `OpenD.xml` is
  GENERATED at runtime from that template + the keyring, contains the password,
  and is gitignored.

## Power BI export contract (Power BI queries depend on it)

- Command: `pipenv run python -m source.export_powerbi` (add `--no-enrich` to skip
  yahoo sector/industry lookups; the daily batch uses `--no-enrich`).
- Eight CSV files exported: dim_date, dim_symbol, fact_snapshots, fact_positions,
  fact_cashflow, fact_trades, fact_benchmark, fact_prices.
- `fact_prices` grain: one Close per ever-held equity per market day, windowed to
  snapshot inception; columns `Date, Symbol, Close`. Sourced from
  `symbol_price_history` (yfinance, auto-adjusted), refreshed by the daily batch
  (`update_symbol_prices_for_positions` in main.py update_db).
- `powerbi/symbol_meta.json` caches yfinance sector/industry (regenerable,
  gitignored).

## Conventions

- User owns git commits.
- The dashboard never writes to the database. Refresh goes through `main.py`
  (run_daily.bat, or the sidebar button which shells out to it).
- Power BI report is saved as PBIP (TMDL) under powerbi/: the Report/ and
  SemanticModel/ definition folders ARE committed (that is the point of PBIP);
  machine-local files are NOT: **/.pbi/ (caches + securityBindings credential blob),
  StaticResources/, *.abf.

## Power BI learning project

- The user must do ALL Power Query / DAX / modeling / visual work hands-on.
- Agent helps user learn, data plumbing if needed
- The learning path lives in `powerbi/POWERBI_ROADMAP.md`
- Learning journal: `powerbi/PowerBI/NOTES.md` — written by the USER only (agent may
  not ghostwrite it).
- Checkpoint screenshots live in `powerbi/PowerBI/Media/`.
