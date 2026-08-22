# Stock Portfolio project — agent guide (source of truth)

User rule (Aug 2026): update this file whenever a design decision changes. It is
the project spec for AI-assisted sessions. Related: `stock-portfolio-tracker` skill
and `powerbi/POWERBI_ROADMAP.md`.

## Architecture

- Data pipeline: moomoo OpenD -> main.py -> SQLite (`db/moomoo_portfolio.db`).
- Two output layers on the SAME database:
  1. Streamlit dashboard (live, operational): `streamlit_app.py`
  2. Power BI analysis/reporting layer: `source/export_powerbi.py` ->
     `powerbi/export/*.csv` (the star-schema contract between SQLite and Power BI)

## Power BI export contract (keep stable — user's Power BI queries depend on it)

- Command: `pipenv run python -m source.export_powerbi` (add `--no-enrich` to skip
  yahoo sector/industry lookups; the daily batch uses `--no-enrich`).
- Seven files: dim_date, dim_symbol, fact_snapshots, fact_positions,
  fact_cashflow, fact_trades, fact_benchmark.
- Every fact table carries `Date` = YYYY-MM-DD; files are utf-8-sig (BOM).
- Amounts stay in the as-reported currency (mostly USD) — mixed-currency modeling
  is a deliberate Power BI learning item.
- fact_benchmark is windowed to snapshot inception (was 98k rows back to 1927);
  fact_positions `Portfolio_Percent` is exported as TEXT (deliberate Power Query
  exercise); `CashflowCategory` already derived (External Capital / Investment
  Income / Internal).
- `powerbi/symbol_meta.json` caches yfinance sector/industry (regenerable,
  gitignored). ODBC direct-to-SQLite is deliberately deferred to a later learning
  phase.

## Conventions

- Keep edited files LF in the working tree (git stores LF; autocrlf unset, no
  .gitattributes). CRLF round-trips produce whole-file diffs.
- New UI strings must be ASCII-only (emoji/surrogate escapes break Streamlit
  protobuf on Windows).
- No ALL-CAPS text in any UI or report. Dark, quiet aesthetic; gold #D4AF37
  accent only for interactive highlights (user design taste).
- Credentials live outside the repo (host ~/.ssh). Never read or print them.
- User owns git commits. Generated artifacts are gitignored: db/, powerbi/export/,
  powerbi/*.pbix, powerbi/symbol_meta.json, daily logs, run_daily.bat.
- Power BI report is saved as PBIP (TMDL) under powerbi/: the Report/ and
  SemanticModel/ definition folders ARE committed (that is the point of PBIP);
  machine-local files are NOT: **/.pbi/ (caches + securityBindings credential blob),
  StaticResources/, *.abf.
- Tests: `python -m pytest tests/ -q` (23 tests). Docker needs
  `pip install pandas yfinance python-dotenv pytest` first.

## Power BI learning project (user rule)

- The user must do ALL Power Query / DAX / modeling / visual work hands-on.
- Agent supplies: data plumbing, exercises, concept explanations, and reviews of
  M/DAX the user pastes. Never write finished Power Query/DAX solutions and never
  open or edit the user's .pbix (learning is the point).
- The learning path lives in `powerbi/POWERBI_ROADMAP.md` (phases + checkpoints).

## Current known improvements (see skill references for full roadmap)

- Risk/vol/drawdown measures (in Power BI first, Streamlit later)
- Gaps: daily refresh chain (snapshot currently stale unless main.py runs);
  per-day FX snapshot table for reproducible historical NAV.