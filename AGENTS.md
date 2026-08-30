# Stock Portfolio project


## Architecture

- Data pipeline: moomoo OpenD -> data cleaning -> main.py -> SQLite (`db/moomoo_portfolio.db`).
- Two output layers on the SAME database:
  1. Streamlit dashboard (live, operational): `streamlit_app.py`
  2. Power BI analysis/reporting layer: `source/export_powerbi.py` ->
     `powerbi/export/*.csv`, `Stock Portfolio project\powerbi\PowerBI` powerBI project files with images

## Power BI export contract (Power BI queries depend on it)

- Command: `pipenv run python -m source.export_powerbi` (add `--no-enrich` to skip
  yahoo sector/industry lookups; the daily batch uses `--no-enrich`).
- Seven CSV files exported: dim_date, dim_symbol, fact_snapshots, fact_positions,
  fact_cashflow, fact_trades, fact_benchmark.
- `powerbi/symbol_meta.json` caches yfinance sector/industry (regenerable,
  gitignored).

## Conventions

- Credentials live outside the repo (host ~/.ssh). Never read or print them.
- User owns git commits.
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
