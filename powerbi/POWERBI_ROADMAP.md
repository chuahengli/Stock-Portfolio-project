# Power BI Learning Roadmap — Stock Portfolio project

> Project status: **ALL PHASES COMPLETE** (Phases 0–5, finished 1 Sep 2026).
> Remaining open items: TE/IR N≥20 floor decision, optional Phase 6 design.
> This file is the course contract + archive. The learning journal lives in
> `PowerBI/NOTES.md` (user-owned).

## Where you stand (updated 1 Sep 2026)

| Phase | Topic | Status |
| ----- | ----- | ------ |
| 0 | Setup | DONE 23 Aug |
| 1 | Get Data + Power Query | DONE (beyond spec: TWR index-merge, AssetSubclass mapping) |
| 2 | The Model (star schema) | DONE (beyond spec: m:1 safety, noise hiding, date-table marking) |
| 3 | DAX | DONE (roadmap measures 1–7 + 6 more, window system, QA'd vs Python targets) |
| 4 | The Report | DONE (3 pages: Overview, Risks, Trades; heatmap, histogram, treemap shipped 1 Sep) |
| 5 | Refresh & Delivery | DONE (Folder-connector swap, PDF export; Service publish declined by choice) |

Open decisions / optional next steps:

- TE/IR on the 1M tile print noise (paired N=5 clears the N<2 floor). Fix is a
  one-line floor raise to N≥20 in both measures — do it whenever it bothers you.
- Phase 6 candidates (design together when wanted): research-folder tickers,
  FX snapshots, an RLS drill, SQLite via ODBC.
- User decisions on record (do not re-suggest): rolling 30-day vol (30 Aug),
  Top-5 weight / concentration (31 Aug), Income & Capital page (1 Sep),
  Power BI Service publish (1 Sep).

## Folder map

```
powerbi/
├── POWERBI_ROADMAP.md          this file — course contract + archive
├── verify_export.py            CSV contract checker (columns, BOM) — run from project root
├── verify_te_ir.py             Python replication of TE/IR DAX for QA targets
├── symbol_meta.json            yfinance sector/industry cache (gitignored, regenerable)
├── export/                     8 star-schema CSVs — GENERATED, never hand-edit
│   ├── dim_date.csv  dim_symbol.csv
│   ├── fact_snapshots.csv  fact_positions.csv  fact_cashflow.csv
│   ├── fact_trades.csv  fact_benchmark.csv  fact_prices.csv
└── PowerBI/                    the PBIP project (open Stock Portfolio PowerBI.pbip)
    ├── NOTES.md                learning journal — USER-owned, agent never writes it
    ├── Media/                  checkpoint screenshots + final PDF export
    ├── Matte Circuit.json / Metricalist - Simply Modern Dark.json   themes
    ├── Stock Portfolio PowerBI.Report/          report definition (PBIP/TMDL)
    └── Stock Portfolio PowerBI.SemanticModel/   model + DAX definition (PBIP/TMDL)
```

PBIP note: Report/ and SemanticModel/ definitions ARE committed (that is the
point of PBIP). Machine-local files are NOT: `**/.pbi/`, `StaticResources/`,
`*.abf`.

## Read this first (the deal)

The point of this track is that YOU build the Power BI skill. I (Hermes) build the data
plumbing — the export script, the clean CSVs, this guide — and you do all of the Power BI
Desktop work with your own hands: connecting, transforming, modeling, DAX, visuals.

The rule: if you can type it, you must type it. I explain concepts, review your M/DAX,
and unblock you when you are genuinely stuck. I will never hand you a finished measure or
a finished .pbix. That is the point.

Ground rules
1. Do NOT hand-edit the CSV exports in Excel or Notepad. Fix the pipeline (or Power
   Query) instead; hand edits vanish on the next refresh and teach nothing.
2. Do NOT rename the export files or their columns behind the course's back. The whole
   guide references them by name.
3. Each phase ends with a Check: send me proof (a screenshot saved into
   `PowerBI/Media/`, your written M line, or a one-sentence answer). I review
   it, then we move on. Log what you did and learned in `PowerBI/NOTES.md` —
   that file is yours alone; I never write in it.
4. Stuck longer than ~20 minutes? Use the Blocker protocol at the bottom.
5. Exports are generated from the SQLite database. On your Windows machine:
       pipenv run python -m source.export_powerbi
   (add `--no-enrich` to skip the Yahoo sector/industry lookup — the daily batch sets
   this already). Re-run that command to refresh the CSVs before working in Power BI.

## The export contract (know this cold)

| File            | Row grain                         | Key columns
| --------------- | --------------------------------- | -----------
| dim_date        | one row per calendar day          | Date, Year, Quarter, QuarterLabel, Month, MonthName, Day, Weekday, WeekdayName, IsWeekend
| dim_symbol      | one row per symbol ever traded    | Symbol, AssetClass, IsOption, Underlying, Multiplier, Name, Market, Currency, Sector, Industry
| fact_snapshots  | one row per tracked day           | Date, total_assets, stocks, options, cash, nav, units
| fact_positions  | one row per symbol per tracked day| Date, Symbol, Name, Market, Quantity, Market_Value, Diluted_Cost, P_L, Today_s_P_L, Currency, Portfolio_Percent
| fact_cashflow   | one row per cash-flow event      | Date, Currency, Type, in_out, Amount, Remark, is_external, is_income, CashflowCategory
| fact_trades     | one row per filled order         | date_time, Date, Symbol, Market, Buy_Sell, Quantity, Fill_Price, Multiplier, Gross_Amount, Currency
| fact_benchmark  | one row per index per day (windowed) | Date, Symbol, Close
| fact_prices     | one row per ever-held equity per market day (windowed) | Date, Symbol, Close

Conventions: every fact table has a Date column formatted YYYY-MM-DD. Files are UTF-8
with BOM, which is why they open cleanly in Excel and Power BI. Amounts stay in
whichever currency moomoo reported (almost all USD, a few SGD) — the mixed-currency
question is deliberately left for you.

Deliberately messy (your classroom):

- Portfolio_Percent in fact_positions is TEXT like "6.93%". Real exports are messy;
  fixing this is your first Power Query job.
- Some dim_symbol sectors are blank. ETFs and a few exotic symbols have no sector on
  Yahoo — real-world dirt; you decide what to do with nulls.
- ^GSPC, ^IXIC, ^FTSE live in fact_benchmark but have no dim_symbol row. Note this;
  it matters in Phase 2.
- Gross_Amount in fact_trades is signed already (BUY negative, SELL positive, options
  x100) — but verifying it yourself is the exercise.

---

# The phases (archive + exercises)

Phases 0–5 are complete. Each phase below keeps: its original exercises (worth
re-reading — they encode the why), the checkpoint definition, and a short
outcome note on what was actually built.

## Phase 0 — setup (one session, ~15-30 min) — DONE 23 Aug

1. Install Power BI Desktop (free) from powerbi.microsoft.com/desktop. The free
   Desktop tier is enough for the whole course; a Pro license matters only when you
   publish to the Power BI cloud (Phase 5, optional).
2. Open the app. Get familiar with the three areas: Report view, Data view, Model
   view (icons on the left edge).
3. Click Get Data in the Home ribbon — the button you will press thousands of times
   in your career. Cancel out of the dialog afterwards.

Checkpoint 0 (send me): one line saying you can open the Report view, the Data view,
and the Model view.

## Phase 1 — Get Data + Power Query (the connector skill) — DONE, beyond spec

> Outcome: all exercises completed; also built the fact_snapshots index-merge for
> the nav TWR column (same pattern as step 6) and the AssetSubclass mapping to
> fill blank sectors/industries. Sources later upgraded to the Folder connector
> (Phase 5) — keep that in mind when reading "Text/CSV" below.

Real data is never clean. Interviewers at VSMC will probe exactly this — "what do you
do with a dirty export?" This phase builds that instinct.

Do these in order, and write one sentence per exercise about what surprised you.

1. Load the 7 files as 7 tables. Get Data > Text/CSV; pick each file in the export
   folder one at a time, choose Transform Data (not Load). Rename each query to:
   dim_date, dim_symbol, fact_snapshots, fact_positions, fact_cashflow, fact_trades,
   fact_benchmark. You should end with 7 named queries. (Do NOT use the Folder
   connector's Combine Files — that merges tables, wrong here.)
2. Type audit. Open fact_trades and inspect the data types Power BI guessed. Which
   columns are text? Which are numbers? What does date_time look like vs Date?
3. Fix Portfolio_Percent. In fact_positions, transform "6.93%" into 0.0693. Steps:
   Replace Values ("%" -> ""), change type to Decimal, then divide by 100 with a
   custom column. Do the replace via the UI, then redo the same "divide" with Add
   Column > Custom Column and compare the two M expressions in the formula bar.
   Keep the clean version (remove the wrong one).
4. Data profiling. In Power Query Editor, View ribbon > Column profile. On
   fact_trades: which columns have nulls? Errors? Look at Quantity — zero-quantity
   rows would poison a measure. Which are options (Multiplier 100)?
5. Calendar enrichment. In dim_date, add YearMonth such as "2026-04"
   (Add Column > From Date, or custom M Date.ToText([Date], "yyyy-MM")). Also add
   MonthShort ("Apr"). Keep numeric Year and Month — charts sort by them.
6. Index-merge (the classic pattern). In fact_benchmark: sort by Date ascending, add
   an Index column (from 0). Duplicate the query; in the copy rename Index to
   PrevIndex and set PrevIndex = [Index] + 1. Merge the original with the copy on
   Index = PrevIndex (keep only rows that match); expand PrevClose only. Add
   DailyReturn = (Close - PrevClose) / PrevClose. This index-shift-merge is THE
   universal pattern for "previous row" in Power Query. Unless truly stuck for 20
   minutes, do not google it — finding the merge order is the exercise.
7. Trades sanity. In fact_trades: BUY rows must have Gross_Amount < 0, SELL > 0.
   Which rows have Multiplier 100, and do their amounts look ~100x sensible? Find a
   SELL_SHORT row; is it positive (cash in)?
8. Open dim_symbol: how many stocks vs options? Which sectors are blank? Why would
   S63 have no sector? (old SGX ticker, no Yahoo metadata.)

Checkpoint 1 (send me): (a) screenshot of Power Query left pane with your 7 named
queries, (b) the M lines you wrote for steps 3 and 5, (c) the most surprising thing
from steps 4 or 6.

## Phase 2 — the model (star schema, cardinality, interview lore) — DONE, beyond spec

> Outcome: all 7 relationships built; many-to-one safety on dim_date→fact_snapshots;
> noise columns hidden; dim_date marked as date table. Later additions in Phase 3:
> the Performance (UNION) and Drawdown calculated tables and their date wiring —
> logged in NOTES Checkpoint 3.

The star structure is in the file naming; your job is to make Power BI believe it.

1. Open the Model view (left-hand icon).
2. Build relationships:
   - dim_date[Date] 1..* fact_snapshots[Date]
   - dim_date[Date] 1..* fact_positions[Date]
   - dim_date[Date] 1..* fact_cashflow[Date]
   - dim_date[Date] 1..* fact_trades[Date]
   - dim_date[Date] 1..* fact_benchmark[Date]
   - dim_symbol[Symbol] 1..* fact_positions[Symbol]
   - dim_symbol[Symbol] 1..* fact_trades[Symbol]
   Do NOT connect dim_symbol to fact_benchmark (^GSPC has no dim_symbol row).
3. Mark as date table: click dim_date, Table tools > Mark as date table, column
   Date. Verify the calendar icon appears. Write one sentence: why does time
   intelligence require one contiguous marked date table?
4. Hide noise: hide columns you won't use (e.g. cashflow_id; the raw is_external /
   is_income flags once CashflowCategory exists). Hiding keeps the field list clean.
5. Relationship autopilot: Power BI may auto-detect relationships. Inspect each —
   cardinality and cross-filter direction. Delete any you didn't create and rebuild
   deliberately.

Checkpoint 2 (send me): Model-view screenshot with all 7 relationships, your
one-sentence answer to "what does a star schema buy you in a report?", the list of
hidden columns, and your note on why ^GSPC has no dim_symbol row.

## Phase 3 — DAX (the paycheck skill) — DONE, beyond spec

> Outcome: original measures 1–7 built, plus six more beyond the roadmap
> (measures 8–13 in NOTES): the window/date-picker system (Period buttons +
> CustomDates slider + WindowStart/Window End), AsOf variants, portfolio +
> benchmark volatility with dynamic annualisation, the rebased
> growth-vs-benchmarks line chart (Performance UNION table + single Growth
> measure, works with multi-select), and the Drawdown calculated table.
> Full DAX + reasoning in NOTES Checkpoint 3. All card numbers QA-verified
> against Python-recomputed targets (verify_te_ir.py) on 31 Aug.

Primer — read once, revisit when measures misbehave:
- Measure: named formula evaluated in filter context; recomputed as you slice.
  Calculated column: per-row stored value; use measures first.
- CALCULATE(expr, filter1, filter2, ...) = recompute expr within modified filters.
- ALL(table) = ignore the filters coming from the visual/context.
- VAR x = ...; RETURN ... = name intermediate values; your life raft.
- MAX(dim_date[Date]) = the last date in the current context.
- LASTNONBLANK(date_col, expr) = the latest date that actually returns a value.

Build a new page, drop a few Card visuals, then create these measures. Write them
wrong on purpose first where told — an error now is a debug skill later.

1. **Total Assets (all history)** = CALCULATE(SUM(fact_snapshots[total_assets]),  [DONE]
   ALL(dim_date)). Run it before and after adding the ALL part and watch the card
   change. Understand what ALL did.
2. **Latest Total Assets** — the classic:  [DONE — later extended with the window filter]
   Latest Total Assets =
   VAR LatestDay =
       CALCULATE(MAX(dim_date[Date]),
           LASTNONBLANK(dim_date[Date],
               CALCULATE(SUM(fact_snapshots[total_assets]))))
   RETURN
       CALCULATE(SUM(fact_snapshots[total_assets]),
           dim_date[Date] = LatestDay)
   Type it, make it work. Then replace the SUM inside LASTNONBLANK with a literal 1
   and observe (hint: LASTNONBLANK needs a real expression; that's the lesson).
3. **Income to date** (running total):  [DONE — as Dividend and Interest Income All Time]
   Income All Time =
       CALCULATE(SUM(fact_cashflow[Amount]),
           fact_cashflow[CashflowCategory] = "Dividend Income"),
           FILTER(ALL(dim_date[Date]), dim_date[Date] <= MAX(dim_date[Date])))
   Narrate while typing: "for every selected day I clear the date filter, keep days
   up to this current day, keep only income rows, then sum." This three-part shape is
   the running-total pattern.
4. **Asset-class weight**:  [DONE — evolved into Stocks/Options/Cash Mix + Ratios +
   AsOf variants, plus Allocation (industry/sector/geography) with DisplaySector /
   DisplayIndustry fallbacks]
   Total Value = SUM(fact_positions[Market_Value])
   Weight =
       DIVIDE([Total Value],
           CALCULATE([Total Value], ALL(dim_symbol)))
   First write Weight WITHOUT the CALCULATE/ALL and see it return 100% for every
   slice. Write down why the denominator must see ALL symbols. Note: positions are
   mostly USD; label the measure "USD basis" for honesty.
5. **Net trade cash flow** = SUM(fact_trades[Gross_Amount]).  [DONE — matrix by
   Currency x Buy_Sell, column subtotals only so SGD and USD don't mix] Slice by Buy_Sell
   (SELL vs BUY) and read the numbers. This is realized net cash flow, NOT realized
   P/L (true realized P/L needs lot-matching — say this distinction aloud).
6. **Volatility, annualized** — needs your Phase 1 DailyReturn column:  [DONE —
   symbol-specific via matrix rows; hardcoded SQRT(252) later replaced by your own
   dynamic N = count/years formula for the sparse portfolio snapshot series.
   Verified: portfolio ~49% (options-driven) vs ^GSPC ~14%]
   Annualized Vol = STDEVX.P(fact_benchmark, fact_benchmark[DailyReturn]) * SQRT(252)
   But: ^GSPC, ^IXIC, ^FTSE all sit in the same table; a sliced report looks
   wrong. Think what should change to make it index-specific, write your idea down,
   then ask me to review it before changing the code.
7. **Drawdown (the stretch boss)** — DONE 29 Aug, by a cleaner route than the
   scaffold below: a Drawdown CALCULATED TABLE (ADDCOLUMNS over
   ALL(Performance[Date]); Level = Portfolio level that day; PeakSoFar = max
   level up to that date; blank-Level rows filtered out), then
   DrawdownPct = DIVIDE(SUM(Drawdown[Level]), SUM(Drawdown[PeakSoFar])) - 1
   and a window-aware "Drawdown %" = CALCULATE([DrawdownPct], KEEPFILTERS(
   window over dim_date)) plotted on Overview. Why the calculated table wins
   over the inline EARLIER measure: the running peak is materialised once
   instead of recomputed per point, the window is one reusable wrapper, and
   future risk measures can build on the same table. One honest caveat: Level
   for the Portfolio series is raw nav, so a cash deposit can print a new
   all-time peak — if that ever bothers you, re-base the table on the
   Time-Weight Return column instead. (The tell-me-what-EARLIER-does exercise
   retired with this build.)
   Strategy for reference — running peak vs today:
   Drawdown % =
   VAR CurrentDay = MAX(dim_date[Date])
   VAR Peak =
       CALCULATE(
           MAXX(
               FILTER(ALL(dim_date[Date]), dim_date[Date] <= CurrentDay),
               CALCULATE(SUM(fact_snapshots[total_assets]), dim_date[Date] <= EARLIER(dim_date[Date]))
           ),
           ALL(dim_date)
       )
   RETURN
       DIVIDE(SUM(fact_snapshots[total_assets]) - Peak, Peak)
   Kept for reference only — you already shipped the better calculated-table
   version above.

Checkpoint 3: DONE — NOTES.md Checkpoint 3 documents measures 1-13, including
the window rewrite and the Performance/Drawdown architecture decisions.

## Phase 4 — the report (your taste, applied) — DONE 1 Sep

> Outcome: three pages shipped (Overview, Risks, Trades), all normalized to
> 1280x720 canvas. Risks carries the full risk stack: portfolio + benchmark vol,
> Max Drawdown, Beta vs ^GSPC, Sharpe (4% rf), Sortino, Historical VaR 95%,
> Expected Shortfall 95%, Calmar, Tracking Error, Information Ratio, correlation
> heatmap, daily-returns histogram, symbol allocation treemap. Allocation merged
> into Risks (user decision); Income & Capital page declined (user decision).
> Layout + per-visual detail: NOTES Phase 4 section + Checkpoint 4 evidence.

Current pages (verified in the saved .Report JSON):
- "Overview": Period button slicer, CustomDates slider, Latest Total Assets card,
  Stocks/Options/Cash Ratio AsOf card, asset-mix line chart, sector + country bar
  charts, rebased Growth-vs-benchmarks line (Performance legend + Symbol slicer),
  and the Drawdown % line. Window machinery applies to all of it.
- "Risks": the measure cards, benchmark vol matrix, correlation heatmap, drawdown
  area chart, allocation bars, histogram, treemap.
- "Trades": Trading Ledger table, Net Trade Cash Flow matrix, Period buttons,
  CustomDates slicer.
Dark theme registered: Metricalist - Simply Modern Dark (+ Matte Circuit.json).

Checkpoint 4: DONE — screenshots of every page in Media/, PDF exported (Phase 5).

## Phase 5 — refresh, delivery, street cred — DONE 1 Sep

> Outcome:
> 1. Manual refresh loop proven: `pipenv run python main.py` (host-side, needs
>    OpenD) → `pipenv run python -m source.export_powerbi --no-enrich` → Refresh
>    in Desktop. Verified end-to-end in the sandbox (all 8 CSVs regenerated).
> 2. Folder refresh SHIPPED: all queries (8 main + prev-day helpers) now source
>    via `Folder.Files(…){[Name="file.csv"]}[Content]` — zero hardcoded absolute
>    paths left in the model. The combine-free shape kept: each file remains its
>    own query. This is the shape VSMC would use for a daily report.
> 3. Power BI Service: DECLINED by user decision — PDF export is the delivery
>    artifact instead (Media/Stock Portfolio PowerBI pdf Export.pdf, linked from
>    NOTES Phase 5).
> 4. Optional later: SQLite directly via ODBC (System DSN) — ask when wanted.
> 5. PDF into the Portfolio Site assets folder later (separate existing pipeline).

The original step-by-step is preserved above in the outcome notes; re-read it if
re-building from scratch.

## VSMC pacing answer (when they ask "how long to pick it up?")

Honest and project-grounded version for your interview:
"I already have real portfolio data, and I am building my own Power BI report on it
end to end right now — Get Data, Power Query cleaning, a proper star-schema model
and DAX measures. I expect the fundamentals to be comfortable within my first two
weeks of part-time practice, and a polished report done in about a month. After that,
your schema and KPI definitions are the fast part, because the toolset becomes a
reflex."
Say it in your own words; the load-bearing ideas: existing real data, end-to-end
ownership, a concrete date.

## Blocker protocol

1. Try yourself 15-20 minutes first.
2. Write exactly: "I tried X, expected Y, got Z, error text: ..." + a screenshot
   (don't include your blind guesses).
3. Send it. I explain the concept, then we find where your logic diverges; you retype
   the fix yourself. If the blocker is a concept — not a bug — ask before the timer;
   the concept battle is the valuable part.

## Quick reference (cheat notes)

Power Query (M): Table.AddColumn, Table.TransformColumnTypes, Table.SelectRows,
Table.AddIndexColumn, Table.RemoveColumns, Text.Replace, Text.BeforeDelimiter,
Text.Trim, Date.Year/Month/Day, Date.ToText, Number.From/Number.FromText,
Table.Merge + Table.ExpandTableColumn.

DAX: CALCULATE, FILTER, ALL, ALLSELECTED, VALUES, SUM, SUMX, STDEVX.P, FIRSTDATE,
LASTDATE, LASTNONBLANK, MAX/MIN, DIVIDE, SELECTEDVALUE, VAR/RETURN.

Phase 6 (when wanted): research-folder tickers, FX snapshots, or an RLS drill —
your call.
