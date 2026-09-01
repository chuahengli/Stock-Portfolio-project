# Power BI Learning Notes

My own record of what I did, what surprised me, and what I decided.
Written in my own words.

Screenshots live in `Media/` and are linked from here.

How I use this file: at each checkpoint, fill the matching section before moving on.

## Conventions

- Screenshots: `Media/Checkpoint N - <topic>.png`, linked below.

## Contents

- [Phase 0 — Setup](#phase-0--setup)
- [Phase 1 — Get Data + Power Query](#phase-1--get-data--power-query)
  - [Checkpoint 1](#checkpoint-1)
- [Phase 2 — The Model](#phase-2--the-model)
  - [Checkpoint 2](#checkpoint-2)
- [Phase 3 — DAX](#phase-3--dax)
  - [Checkpoint 3](#checkpoint-3)
  - [Measure 1 — Total Assets (all history)](#measure-1--total-assets-all-history)
  - [Measure 2 — Latest Assets](#measure-2--latest-assets)
  - [Measure 3 — Income to date](#measure-3--income-to-date)
  - [Measure 4 — Asset Class Weight](#measure-4--asset-class-weight)
  - [Measure 5 — Industry, Geography](#measure-5--industry-geography)
  - [Measure 6 — Net Trade Cash Flow](#measure-6--net-trade-cash-flow)
  - [Measure 7 — Benchmark Volatility](#measure-7--benchmark-volatility)
  - [Measure 8 — Portfolio Volatility](#measure-8--portfolio-volatility)
  - [Measure 9 — Date Picker](#measure-9--date-picker)
  - [Measure 10 — 3 Ratio AsOf](#measure-10--3-ratio-asof)
  - [Measure 11 — Custom Date Picker](#measure-11--custom-date-picker)
  - [Measure 12 — Performance vs Benchmarks](#measure-12--performance-vs-benchmarks)
  - [Measure 13 — Drawdown](#measure-13--drawdown)
- [Phase 4 — The Report (Design)](#phase-4--the-report-design)
  - [Checkpoint 4](#checkpoint-4)
  - [Risks Page](#risks-page)
  - [Trades Page](#trades-page)
- [Phase 5 — Refresh & Delivery](#phase-5--refresh--delivery)

---

## Phase 0 — Setup

- Done on: 23 Aug 2026
- Notes:

---

## Phase 1 — Get Data + Power Query

### Checkpoint 1

- Evidence:

![Checkpoint 1 queries pane](Media/Checkpoint%201%20-%20Queries.png)

- What I did
  - Imported the csv files as source. Looked through the queries from the csv imported and checked through all the data types. Checked through also all the data types available, making sure that the best possible datatype for each column is accurate. Had to search up, look through google and AI on how to do some things like changing the datatype for the portfolio percentage and divide since the numbers were wrong. Looked through data profiling like the column profile and other things I can tick to see more about the data. So that I can decide which data to filter out that are irrelevant, like those that are empty, 0 should not be there.

- What surprised me
  - I had to create new column query just to make sure to do the previous day benchmark. Thought it would be intelligent enough to be able to use the same query table to edit the previous day inplace. Had to create a new table, merge onto the original and expand then uncheck the enable load.

- Decisions I made and why
  - Kept `fact_benchmark` Prev load-disabled because I did not want to load that as a dataset, since it is just a query created to get the daily benchmark performance
  - Added AssetSubclass mapping because of some tickers like the SG tickers and the ETFs did not have proper sector and industry. They were blank. Hence the AssetSubclass was used to map the tickers to their perspective classification
  - After phase 3, decided to add portfolio nav return column by duplicate, create `fact_snapshot_prev`, same as dailyReturns for `fact_benchmark`.
    - `fact_snapshots`, sort by Date ascending, added index column start from 0
    - Duplicate to create `fact_snapshots_prev`
    - Remove other columns, add prevIndex column, `Prev_Index = Index + 1`
    - Rename nav as Prev_Nav
    - Then join and merge in `fact_snapshots` (Not merge as new)
    - `fact_snapshots` - Index; `fact_snapshots_prev` - Prev_Index; Join Left Outer, Expand only Prev_Nav, untick use original column as name
    - Add custom column `TWR = ([nav]/[Prev_Nav]) - 1`
    - Validated the data with table card

---

## Phase 2 — The Model

### Checkpoint 2

- Evidence:

![Checkpoint 2 model view](Media/Checkpoint%202%20-%20Model%20View%20.png)

- What I did
  - Had trouble knowing what to do in the model view section. Had to search how to do it through youtube, AI, google.
  - Wondered how to decide the cardinality and the filter direction. dim must be linked to the fact tables. Since the dims symbol and date are those that appear in multiple tables that must be linked. Found out we need to decide and look through cardinality if something goes wrong based on the context of the issue
  - Marked `dim_date` as date table. It binds the time-intelligence functions to it. It represents the real time for the whole dataset. This is so that it knows the true date in `dim_date`. As other dates might get skipped from the calculations due to inactive trading days

- What surprised me

- Decisions I made and why
  - `dim_date` to `fact_snapshots` is one to one cardinality, but is both directions. The issue is that both have unique. Snapshots were not taking everyday. So they are not really exact subsets. Snapshots does have one row tracked per day. 1 to 1 is forced to be bidirectional. To keep it safe, I made it many to one. `fact_snapshots` is the many side since it could be possible to have more than 1 snapshot per day.
  - Hiding noise, deciding which one to hide.
    - Hid in `fact_positions`: Name (dim_symbol already)
    - Hid in `fact_cashflow`: is_external, is_income (for python cashflow category)
    - Hid in `fact_trades`: Multiplier (Shown in gross amount, used for calculation in code)

---

## Phase 3 — DAX

### Checkpoint 3

- Evidence:

![Checkpoint 3 — Page 1 Overview](Media/Checkpoint%203%20-%20Page%201.png)

- What I did

#### Measure 1 — Total Assets (all history)

- Add the `Total Assets (all history) = SUM(fact_snapshots[total_assets])` into a card, with like 7.3M which is all assets all dates sum together. Then add another slicer at the side with MonthName (Apr, Aug, ...) to get to click to filter by each month. Clicked Aug got 226K
- `ALL(dim_date)` tells: Before summing, remove all filers. So even if filtered, the number stays the same

#### Measure 2 — Latest Assets

- Created a new card, added a measure on `fact_snapshots` with:

  ```dax
  Latest Total Assets =
  VAR LatestDay =
      CALCULATE(
          MAX(dim_date[Date]),
          LASTNONBLANK(dim_date[Date], CALCULATE(SUM(fact_snapshots[total_assets])))
      )
  RETURN
      CALCULATE(SUM(fact_snapshots[total_assets]), dim_date[Date] = LatestDay)
  ```

  - If `LASTNONBLANK(dim_date[Date], 1)` - gives a blank since there is no value in the date in fact_snapshots given by dim_date

- How it works:
  - Block 1 - `CALCULATE(SUM(fact_snapshots[total_assets]))`: calculate total_assets for that given date. If nothing, blank.
  - Block 2 - `LASTNONBLANK(dim_date[Date], <Block 1>)`: walk through dim_date, asking Block 1 for value each. Keeps one-column one-row table of the last date where it is not blank
  - Block 3 - `CALCULATE(MAX(dim_date[Date]), <Block 2>)`: in the LASTNONBLANK one-column one-row table. Forces to convert to a scalar value. So as to ensure that `VAR LatestDay` works. Without forcing conversion to scalar, works too as it has implicit data type conversion
  - `RETURN CALCULATE(SUM(fact_snapshots[total_assets]), dim_date[Date] = LatestDay)`: calculate the total_assets value on that last non-blank date to be Latest Total Assets

- Alternative that works as well:

  ```dax
  CALCULATE(
      SUM(fact_snapshots[total_assets]),
      LASTNONBLANK(dim_date[Date], CALCULATE(SUM(fact_snapshots[total_assets])))
  )
  ```

#### Measure 3 — Income to date

- Changed how I classified cashflow category in cashflow_table. Some cash coupons and rewards from moomoo now considered income. Renamed it to be dividend income
- Created card with measure:

  ```dax
  Dividend and Interest Income All Time =
  CALCULATE(
      SUM(fact_cashflow[Amount]),
      fact_cashflow[CashflowCategory] = "Dividend Income",
      FILTER(
          ALL(dim_date[Date]),
          dim_date[Date] <= MAX(dim_date[Date])
      )
  )
  ```

- How it works
  - Block 1 - `FILTER(ALL(dim_date[Date]), dim_date[Date] <= MAX(dim_date[Date]))`: from all dim_date[Date], select those that before and including latest date
  - Block 2 - `SUM(fact_cashflow[Amount])` with `fact_cashflow[CashflowCategory] = "Dividend Income"` and Block 1: sum all amount in cashflow that is categorised as "Dividend Income", filter with Block 1. Got dividend income for all time

#### Measure 4 — Asset Class Weight

- This is to get the asset class (stocks, options, cash) weighting
- Created four base measures:

  ```dax
  Stocks Value = SUM(fact_snapshots[stocks])
  Options Value = SUM(fact_snapshots[options])
  Cash Value = SUM(fact_snapshots[cash])
  Component Total = [Stocks Value] + [Options Value] + [Cash Value]
  ```

  - So to explicitly SUM them, such that they can be used date by date in a time series manner. If not it would still be implicitly used as SUM for display purposes.

- Created three ratio measures:

  ```dax
  Stocks Mix = DIVIDE([Stocks Value], [Component Total])
  Options Mix = DIVIDE([Options Value], [Component Total])
  Cash Mix = DIVIDE([Cash Value], [Component Total])
  ```

  - No CALCULATE and ALL, since the numerator should be on the same context (time)

- Added the 3 ratios in cards, then added a date slicer to click. All the percentage sum to 100%
- Added Time series. Line chart with `dim_date[Date]` then added the 3 mixes as values
- Used Component Total since total_assets might not be accurate. Slightly off by 0.5%, though it would still work.

![Checkpoint 3 — Asset Class Line Chart](Media/Checkpoint%203%20-%20Asset%20Class%20Line%20Chart.png)

#### Measure 5 — Industry, Geography

- Added base:

  ```dax
  Positions Value = SUM(fact_positions[Market_Value])
  Allocation =
  DIVIDE(
      [Positions Value],
      CALCULATE([Positions Value], ALL(dim_symbol))
  )
  ```

  - Allocation - numerator can be sliced, denominator cannot be sliced by dim_symbol

- Then for industry allocation, checked DisplayIndustry in the Y-Axis for horizontal bar chart (changed to table after)
- For sector allocation, checked DisplaySector in Y-Axis for horizontal bar chart
- For geographical allocation, checked Country in Y-Axis for horizontal bar chart
- Added Power Query columns:

  ```powerquery
  DisplaySector =
  if [Sector] = null or Text.Trim([Sector]) = ""
      then [AssetSubclass]
      else [Sector]

  DisplayIndustry =
  if [Industry] = null or Text.Trim([Industry]) = ""
      then [AssetSubclass]
      else [Industry]
  ```

  - So the display for the bar charts for allocation could be properly done without blanks. Most of these blanks are the result of Singapore Stocks, ETFs that do not have proper classification in yahoofinance

- With a date slicer on page 1, I decided to change the formula. Since they should always show the latest fact_positions date inside the slicer window, not be double-filtered.
- Decided to keep ONE relative-date slicer on `dim_date[Date]`
- Let the measure pick its own date from inside the window

  ```dax
  Allocation =
  VAR LastDataDay = CALCULATE(MAX(fact_positions[Date]), ALL(dim_symbol))
  RETURN
      DIVIDE(
          CALCULATE(SUM(fact_positions[Market_Value]), fact_positions[Date] = LastDataDay),
          CALCULATE(SUM(fact_positions[Market_Value]), fact_positions[Date] = LastDataDay, ALL(dim_symbol))
      )
  ```

  - LastDataDay: gets the max of `fact_positions[Date]`
  - calculate Market_Value of the LastDataDay only, making it correct
  - Ensures there is no empty calendar days
  - `CALCULATE(SUM(fact_positions[Market_Value]), fact_positions[Date] = LastDataDay)`: sum of the market_value only on the last date, ignoring the multi-select page slicer
  - denominator use `ALL(dim_symbol)` so the slicer does not affect the constant denominator

![Checkpoint 3 — Sector Allocation Bar Chart](Media/Checkpoint%203%20-%20DisplaySector%20Allocation%20Horizontal%20Bar%20Chart.png)

![Checkpoint 3 — Country Allocation Bar Chart](Media/Checkpoint%203%20-%20Country%20Allocation%20Horizontal%20Bar%20Chart.png)

![Checkpoint 3 — Industry Allocation Table](Media/Checkpoint%203%20-%20DisplayIndustry%20Allocation%20Table%20Visualisation.png)

#### Measure 6 — Net Trade Cash Flow

- Tells how much was consumed on trades (not profit loss, as still own shares in things)

  ```dax
  Net Trade Cash Flow = SUM(fact_trades[Gross_Amount])
  ```

- Created a matrix:
  - Rows - `fact_trades[Currency]`
  - Columns - `fact_trades[Buy_Sell]`
  - Values - `fact_trades[Net Trade Cash Flow]`
  - Kept column subtotal, without row subtotal, so they total the currencies separately, as SGD and USD don't mix to total properly

![Checkpoint 3 — Net Trade Cash Flow Matrix](Media/Checkpoint%203%20-%20Net%20Trade%20Cash%20Flow%20Matrix.png)

#### Measure 7 — Benchmark Volatility

- Measure the volatility of each of the benchmarks, so next time can measure against portfolio, beta, sortino, sharpe

  ```dax
  Annualized Vol =
  STDEVX.P(
      fact_benchmark,
      fact_benchmark[DailyReturn]
  ) * SQRT(252)
  ```

- Created a matrix:
  - Rows - `fact_benchmark[Symbol]`
  - Values - `fact_benchmark[Annualized Vol]`
- Added visualisation filter date is on or after 01/01/2026 so it is YTD this year. SP500 got 13.8%

![Checkpoint 3 — Benchmark Annualised Volatility Matrix](Media/Checkpoint%203%20-%20Benchmark%20Annualised%20Volatility%20Matrix.png)

- Measure 13 — Drawdown % evidence (Phase 4, windowed):

![Checkpoint 3 — Drawdown %](Media/Checkpoint%203%20-%20Drawdown%20%.png)

#### Measure 8 — Portfolio Volatility

- Since fact_snapshots for portfolio dont have all dates, need to do variable date calendar things
- N = count of days recorded / years spanned
- Need to do time spanned in years to scale them up to compare appropriately (like 6 mo -> 0.5 years spanned)
- Count of days recorded -> number of days recorded in fact_snapshot that you filtered
- e.g N = 40 days / 6 mo = 40 / 0.5 years = 80

  ```dax
  Portfolio annualized volatility =
  VAR ReturnsCount   = COUNTA(fact_snapshots[Time-Weight Return])
  VAR First_Date     = MIN(fact_snapshots[Date])
  VAR Last_Date      = MAX(fact_snapshots[Date])
  VAR YearSpan       = (Last_Date - First_Date) / 365.25
  VAR PeriodsPerYear = DIVIDE(ReturnsCount, YearSpan)
  VAR Sd             = STDEVX.P(fact_snapshots, fact_snapshots[Time-Weight Return])
  RETURN
      IF(ReturnsCount < 2, BLANK(), Sd * SQRT(PeriodsPerYear))
  ```

#### Measure 9 — Date Picker

- Wanted a proper date picker
- Added table:

  ```dax
  Period =
  DATATABLE(
      "Label", STRING,
      "Sort", INTEGER,
      {
          {"1W", 1},
          {"1M", 2},
          {"3M", 3},
          {"6M", 4},
          {"YTD", 5},
          {"1Y", 6},
          {"2Y", 7},
          {"ALL", 8}
      }
  )
  ```

- Click sort by column: Sort
- Added a button slicer, horizontal with 7 columns. Label: "Period"
- Under Period table, added measure:

  ```dax
  Date Anchor = CALCULATE(MAX(fact_snapshots[Date]), ALL(dim_date), ALL(fact_positions))
  ```

  - To anchor the final date of the selection. Independent of any filter from dim_date and fact_snapshots

- Created another measure:

  ```dax
  WindowStart =
  VAR Anchor = [Date Anchor]
  VAR Label = SELECTEDVALUE(Period[Label])
  RETURN
  SWITCH(
      Label,
      "1W",  Anchor - 7,
      "1M",  EDATE(Anchor, -1),
      "3M",  EDATE(Anchor, -3),
      "6M",  EDATE(Anchor, -6),
      "YTD", DATE(YEAR(Anchor), 1, 1),
      "1Y",  EDATE(Anchor, -12),
      "2Y",  EDATE(Anchor, -24),
      MIN(dim_date[Date])
  )
  ```

  - Last line is the fallback when nothing is selected gives full history (ALL)

- Created another measure:

  ```dax
  IsInWindow =
  VAR S = [WindowStart]
  RETURN
  IF(
      MAX(dim_date[Date]) >= S && MAX(dim_date[Date]) <= [Date Anchor],
      1, 0
  )
  ```

  - If the calendar date is in the window
  - Evaluates row by row. `MAX(dim_date[Date])` is the row's date itself. So check if date is in window.

- Hit a wall, cannot add the IsInWindow to page filter. Because the measures all can't be added to page filters
- Changed the whole page filters:

  ```dax
  Stocks Ratio =
  VAR WindowFilter = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor])
  VAR WindowValue = CALCULATE([Stocks Value], KEEPFILTERS(WindowFilter))
  VAR WindowTotal = CALCULATE([Component Total], KEEPFILTERS(WindowFilter))
  RETURN DIVIDE(WindowValue, WindowTotal)
  ```

  ```dax
  Options Ratio =
  VAR WindowFilter = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor])
  VAR WindowValue = CALCULATE([Options Value], KEEPFILTERS(WindowFilter))
  VAR WindowTotal = CALCULATE([Component Total], KEEPFILTERS(WindowFilter))
  RETURN DIVIDE(WindowValue, WindowTotal)
  ```

  ```dax
  Cash Ratio =
  VAR WindowFilter = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor])
  VAR WindowValue = CALCULATE([Cash Value], KEEPFILTERS(WindowFilter))
  VAR WindowTotal = CALCULATE([Component Total], KEEPFILTERS(WindowFilter))
  RETURN DIVIDE(WindowValue, WindowTotal)
  ```

  ```dax
  Latest Total Assets =
  VAR LatestDay =
      CALCULATE(
          MAX(dim_date[Date]),
          LASTNONBLANK(dim_date[Date], CALCULATE(SUM(fact_snapshots[total_assets]))),
          FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor])
      )
  RETURN CALCULATE(SUM(fact_snapshots[total_assets]), dim_date[Date] = LatestDay)
  ```

  ```dax
  Allocation =
  CALCULATE(
      VAR LastDataDay = CALCULATE(MAX(fact_positions[Date]), ALL(dim_symbol))
      RETURN
          DIVIDE(
              CALCULATE(SUM(fact_positions[Market_Value]), fact_positions[Date] = LastDataDay),
              CALCULATE(SUM(fact_positions[Market_Value]), fact_positions[Date] = LastDataDay, ALL(dim_symbol))
          ),
      FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor])
  )
  ```

  - The window: WindowStart is the start date, and Date Anchor is the latest date the portfolio snapshots has
  - `FILTER(ALL(dim_date[Date]), Date >= [WindowStart] && Date <= [Date Anchor])` is to make it such that the dates are inside the window
  - For the stock, cash, options ratios, numerator and denominator both use the window. KEEPFILTERS keeps the line chart's per-date rows. KEEPFILTERS goes inside CALCULATE and not in VAR
  - Latest Total Assets: last snapshot inside the window
  - measure wrapped in CALCULATE with the window filter, LastDataDay becomes "last position date inside the window"

#### Measure 10 — 3 Ratio AsOf

- Since I want a single last date of window sliced in the 3 ratio card, which is different from the time series of the 3 ratios with multi-selection
- So these are single last date of the window, independent of the 3 ratios initially created

  ```dax
  Stocks Ratio AsOf =
  VAR AsOfDay = CALCULATE(MAX(fact_snapshots[Date]), FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor]))
  RETURN CALCULATE(DIVIDE([Stocks Value], [Component Total]), fact_snapshots[Date] = AsOfDay)
  ```

  ```dax
  Options Ratio AsOf =
  VAR AsOfDay = CALCULATE(MAX(fact_snapshots[Date]), FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor]))
  RETURN CALCULATE(DIVIDE([Options Value], [Component Total]), fact_snapshots[Date] = AsOfDay)
  ```

  ```dax
  Cash Ratio AsOf =
  VAR AsOfDay = CALCULATE(MAX(fact_snapshots[Date]), FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Date Anchor]))
  RETURN CALCULATE(DIVIDE([Cash Value], [Component Total]), fact_snapshots[Date] = AsOfDay)
  ```

  - AsOfDay - last date available in fact_snapshots in the overarching filtered window
  - Numerator and denominator inherit the last day filter

#### Measure 11 — Custom Date Picker

- Wanted a custom date picker together with the button slicer date picker previously
- Created new table:

  ```dax
  CustomDates = CALENDAR(MIN(dim_date[Date]), MAX(dim_date[Date]))
  ```

  - Make sure data type is date dd/mm/yyyy
- Inserted slider visual between
- In Period table previously created:

  ```dax
  Window End =
  VAR CustomEnd = IF(ISFILTERED(CustomDates[Date]), MAX(CustomDates[Date]))
  RETURN IF(ISBLANK(CustomEnd), [Date Anchor], MIN(CustomEnd, [Date Anchor]))
  ```

  ```dax
  WindowStart =
  VAR CustomStart = IF(ISFILTERED(CustomDates[Date]), MIN(CustomDates[Date]))
  VAR Anchor = [Date Anchor]
  VAR Label = SELECTEDVALUE(Period[Label])
  RETURN
  IF(
      NOT ISBLANK(CustomStart),
      CustomStart,
      SWITCH(
          Label,
          "1W",  Anchor - 7,
          "1M",  EDATE(Anchor, -1),
          "3M",  EDATE(Anchor, -3),
          "6M",  EDATE(Anchor, -6),
          "YTD", DATE(YEAR(Anchor), 1, 1),
          "1Y",  EDATE(Anchor, -12),
          "2Y",  EDATE(Anchor, -24),
          MIN(dim_date[Date])
      )
  )
  ```

- Replace Date Anchor with Window End in (3 ratios, Latest Total Assets, Allocation)
- Replaced the last date Date Anchor. The Window End is a moveable date. As custom date makes start and end of the windows moveable
- `ISFILTERED(CustomDates[Date])` = "did the user pick anything?" True with a pick, false when cleared.
- Window End: if nothing picked, equivalent to Date Anchor the last available date. `MIN(CustomEnd, [Date Anchor])` makes sure to pick the min of the 2, doesn't exceed beyond Date Anchor

#### Measure 12 — Performance vs Benchmarks

- Portfolio Growth (new measure, fact_snapshots):

  ```dax
  Portfolio Growth =
  VAR WindowFilter = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR BaseDay = CALCULATE(MIN(fact_snapshots[Date]), WindowFilter)
  VAR BaseNav = CALCULATE(SUM(fact_snapshots[nav]), dim_date[Date] = BaseDay)
  RETURN
  CALCULATE(
      DIVIDE(SUM(fact_snapshots[nav]), BaseNav),
      KEEPFILTERS(WindowFilter)
  )
  ```

  - BaseDay is window's first tracked day
  - BaseNav is nav of the BaseDay
  - Each line point is then nav-that-day / starting-nav x 100 implicitly

- Benchmark Growth:

  ```dax
  Benchmark Growth =
  VAR WindowFilter = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR BaseDay = CALCULATE(MIN(fact_benchmark[Date]), WindowFilter)
  VAR BaseNav = CALCULATE(SUM(fact_benchmark[Close]), dim_date[Date] = BaseDay)
  RETURN
  IF(
      HASONEVALUE(fact_benchmark[Symbol]),
      CALCULATE(
          DIVIDE(SUM(fact_benchmark[Close]), BaseNav),
          KEEPFILTERS(WindowFilter)
      ),
      BLANK()
  )
  ```

  - WindowFilter - the window. `ALL(dim_date[Date])` ignores dim_date date, FILTER keeps date inside the window
  - BaseClose - sum of close on BaseDay. Didn't strip symbol filters, so they can be filtered to each symbol to get that symbol's close. No `ALL(fact_benchmark)`. Stripping will sum all the symbols close
  - RETURN - evaluated once per line point
  - `SUM(fact_benchmark[Close])` = the index's close on that point's date
  - `KEEPFILTERS(WindowFilter)` intersects the window with the row's own date instead of replacing it - without it the filter would wipe the per-date grouping and every point would show the whole window's sum. Same reason the ratio line chart needs it.
  - DIVIDE gives close-that-day / base-close. Start point = 1.00 (=100 base); an index up 8% in the window ends at 1.08
  - Changed a bug `CALCULATE(SUM(fact_benchmark[Close]), dim_date[Date] = BaseDay)`. Included `dim_date[Date]` as it is what was plotted against, replacing `fact_snapshots[Date]` or `fact_benchmark[Date]`

- To create a better line chart to compare not overlap and front and back, created a new table:

  ```dax
  Series =
  UNION(
      ROW("Symbol", "Portfolio"),
      DISTINCT(SELECTCOLUMNS(fact_benchmark, "Symbol", fact_benchmark[Symbol]))
  )
  ```

- New Column in fact_benchmark table. Only for the symbols you ticked in the slicer. When two are selected it keeps both rows. Doesn't rely on 1 value only:

  ```dax
  Series Symbol = IF(fact_benchmark[Symbol] IN VALUES(Series[Symbol]), fact_benchmark[Symbol])
  ```

- One combined measure on fact_benchmark. Replace Portfolio Growth and Benchmark Growth:

  ```dax
  Growth =
  IF(
      NOT HASONEVALUE(Series[Symbol]),
      BLANK(),
      VAR Sym = SELECTEDVALUE(Series[Symbol])
      VAR WindowFilter =
          FILTER(
              ALL(dim_date[Date]),
              dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End]
          )
      RETURN
      IF(
          Sym = "Portfolio",
          CALCULATE(
              VAR BaseDay = CALCULATE(MIN(fact_snapshots[Date]), WindowFilter)
              VAR BaseNav = CALCULATE(SUM(fact_snapshots[nav]), dim_date[Date] = BaseDay)
              RETURN
                  DIVIDE(SUM(fact_snapshots[nav]), BaseNav) * 100,
              KEEPFILTERS(WindowFilter),
              ALL(fact_benchmark)
          ),
          CALCULATE(
              VAR BaseDay = CALCULATE(MIN(fact_benchmark[Date]), WindowFilter)
              VAR BaseClose = CALCULATE(SUM(fact_benchmark[Close]), dim_date[Date] = BaseDay)
              RETURN
                  DIVIDE(SUM(fact_benchmark[Close]), BaseClose) * 100,
              KEEPFILTERS(WindowFilter)
          )
      )
  )
  ```

#### Measure 13 — Drawdown

- Decide to create a new table for the drawdown. Better architecture since it is more modular with more freedom

  ```dax
  Drawdown =
  VAR rowss =
      ADDCOLUMNS(
          ALL(Performance[Date]),
          "Level", CALCULATE(SUM(Performance[Level]), Performance[Symbol] = "Portfolio"),
          "PeakSoFar", CALCULATE(
              MAX(Performance[Level]),
              FILTER(ALL(Performance[Date]), Performance[Date] <= CALCULATE(MAX(Performance[Date]))),
              Performance[Symbol] = "Portfolio"
          )
      )
  RETURN
      FILTER(rowss, NOT ISBLANK([Level]))
  ```

  - ADDCOLUMNS: the Date, Level with data from "Portfolio" only, PeakSoFar column calculate the max level from previous dates

- Create another measure for drawdown percent:

  ```dax
  DrawdownPct = 
  VAR Num = SUM(Drawdown[Level])
  VAR Den = SUM(Drawdown[PeakSoFar])
  RETURN
      IF( ISBLANK(Num),
          BLANK(),
          DIVIDE( Num, Den ) - 1
      )
  ```

  ```dax
  Drawdown % = 
  VAR WindowFilter =
      FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  RETURN
  CALCULATE(
      [DrawdownPct],
      KEEPFILTERS(WindowFilter)
  )
  ```

  - Link with the window filters. Makes sure is in window, and plot that DrawdownPct to the exact without summing
  - Edited the error that the numerator could be blank due to empty day.

---

## Phase 4 — The Report (Design)

> Pages shipped: Overview, Risks, Trades (all 1280x720). Evidence below; per-visual detail in the sections that follow.

### Checkpoint 4

- Evidence:

![Checkpoint 4 — Risks page](Media/Checkpoint%204%20-%20Page%202.png)

![Checkpoint 4 — Trades page](Media/Checkpoint%204%20-%20Page%203.png)

### Risks Page

- Added Window Filtering that is synced with the Overview page
- Added Drawdown % graph in that syncs according to the windowfilter

#### Benchmark Volatility

- Benchmark vol matrix, replaced the:

  ```dax
  Benchmark Volatility =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR N = CALCULATE(COUNTA(fact_benchmark[DailyReturn]), Win)
  VAR FirstD = CALCULATE(MIN(fact_benchmark[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_benchmark[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR Sd = CALCULATE(STDEVX.P(fact_benchmark, fact_benchmark[DailyReturn]), Win)
  RETURN
      IF(N < 2, BLANK(), Sd * SQRT(DIVIDE(N, YearSpan)))
  ```

#### Portfolio Volatility

- Edited portfolio volatility:

  ```dax
  Portfolio Volatility =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR Sd = CALCULATE(STDEVX.P(fact_snapshots, fact_snapshots[Time-Weight Return]), Win)
  RETURN
      IF(N < 2, BLANK(), Sd * SQRT(DIVIDE(N, YearSpan)))
  ```

#### Max Drawdown

- Max drawdown = the worst single point of the line you already have
- Created a new measure in the Drawdown Table

  ```dax
  Max Drawdown =

  MINX(
      VALUES(dim_date[Date]),
      [Drawdown %]
  )
  ```

#### Beta

- Beta against the S&P500
- covariance needs the portfolio return and the benchmark return paired per date, then divided by benchmark variance.
  
  ```dax
  Beta vs ^GSPC =

  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR MeanP = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]), Win)
  VAR MeanB = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), Win, fact_benchmark[Symbol] = "^GSPC")
  VAR Cov =
      CALCULATE(
          AVERAGEX(
              VALUES(dim_date[Date]),
              VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
              VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
              RETURN IF(ISBLANK(Rp) || ISBLANK(Rb), BLANK(), (Rp - MeanP) * (Rb - MeanB))
          ),
          Win
      )
  VAR VarB = 
      CALCULATE(
          AVERAGEX(
              VALUES(dim_date[Date]),
              VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
              RETURN IF(ISBLANK(Rb), BLANK(), (Rb - MeanB) ^ 2)
          ),
          Win
      )
  RETURN DIVIDE(Cov, VarB)
  ```

  - Cov - Covariance between portfolio and benchmark.
  - AVERAGEX - That line walks the list date by date, averages all the non-blanks.
  - Rp calculate the portfolio returns of that day since it is inner CALCULATE.
  - The blank guard is so the blanks are omitted by averagex
  - RETURN (Rp - MeanP) * (Rb - MeanB) is Cov
  - RETURN DIVIDE(Cov, VarB) is variance of benchmark
  
- 

#### Sortino Ratio

- Sortino Ratio:

  ```dax
  Sortino Ratio = 
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR MeanP = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]), Win)
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR PeriodsPerYear = DIVIDE(N, YearSpan)
  VAR DownDev =
    CALCULATE(
        AVERAGEX(
            VALUES(dim_date[Date]),
            VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
            RETURN IF(ISBLANK(Rp), BLANK(), MIN(Rp, 0) ^ 2)
        ),
        Win
    )

  RETURN
      IF(N < 2, BLANK(), DIVIDE(MeanP * PeriodsPerYear, SQRT(DownDev) * SQRT(PeriodsPerYear)))
  ```

- Included, the Win, Window filter, same stuff as portfolio vol, inculuded MeanP from Beta
- Var DownDev similar to Cov of Beta. Min() so negative is squared, positives are 0
- sqrt downdev to get actual deviation not variance. Same guard of N < 2 , BLANK()
- Average over all dates, not just negative ones.

#### Sharpe Ratio

  ```dax
  Sharpe Ratio =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR MeanP = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]), Win)
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR PeriodsPerYear = DIVIDE(N, YearSpan)
  VAR AnnualReturn = MeanP * PeriodsPerYear
  RETURN IF(N < 2, BLANK(), DIVIDE(AnnualReturn - 0.04, [Portfolio Volatility]))
  ```

- Numerator: same MeanP * PeriodsPerYear, minus risk-free rate.
- Set as a constant 4%
- Use Portfolio Volatility measure that was created already.

#### VaR

- Value at Risk
- Question it answers: "on a bad day, how bad?"
- Decided to use Historical VaR, not parametric or Monte Carlo
- Inputs: fact_snapshots[Time-Weight Return] within Win
- Take the actual daily returns, find 5th percentile (95 % confidence)
- Historical Value at Risk (95%)

  ```dax
  Historical VaR 95% =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR Q = CALCULATE(
      PERCENTILEX.INC(
          fact_snapshots,
          fact_snapshots[Time-Weight Return],
          0.05
      ),
      Win
  )
  RETURN IF(N < 20, BLANK(), Q)
  ```

- Take Win as usual to be windowed filter
- N is number of return rows counts in window filter
- Calculate 5th percentile ...

#### Calmar Ratio

- Question it answers: return per unit of worst pain (no risk-free rate needed)
- Inputs: CAGR (may not exist yet as a measure) and [Max Drawdown]
- CAGR must be geometric
- Guards:
  - N < 2
-

  ```dax
  Calmar Ratio =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR NavFirst = CALCULATE(SUM(fact_snapshots[nav]), dim_date[Date] = FirstD)
  VAR NavLast = CALCULATE(SUM(fact_snapshots[nav]), dim_date[Date] = LastD)
  VAR CAGR = IF(YearSpan > 0, DIVIDE(NavLast, NavFirst) ^ DIVIDE(1, YearSpan) - 1)
  VAR Mdd = [Max Drawdown]
  RETURN IF(N < 2 || ISBLANK(Mdd) || Mdd = 0, BLANK(), DIVIDE(CAGR, -Mdd))
  ```

- NavFirst, NavLast, gives value of NAV of FirstD and LastD same as Portfolio Growth measure
- VAR CAGR = IF(YearSpan > 0, DIVIDE(NavLast, NavFirst) ^ DIVIDE(1, YearSpan) - 1) ->  (end/start)^(1/years) − 1 finds and annualises the growth rate based on start and end window. IF(YearSpan > 0..) so that it doesn't evaluate if YearSpan is 0 or BLANK.
- IF(N < 2 || ISBLANK(Mdd) || Mdd = 0, BLANK(), DIVIDE(CAGR, -Mdd)) -> Same N>2 guard. Check if Mdd is blank or 0 then BLANK(). -Mdd since Mdd is always negative. So can divide the ratio properly

#### Tracking Error

- Question it answers: "how different am I actually from the index?"
- Distinctness of portfolio volatility, not better or worse per se
- Inputs: daily portfolio return (fact_snapshots[Time-Weight Return]), daily benchmark return (fact_benchmark[DailyReturn], one Symbol — likely ^GSPC)
- SD of the difference between portfolio and benchmark
- Pattern: same skeleton as the vol measures — Win filter, N, FirstD/LastD, YearSpan — but the stdev runs over the daily difference, not the raw return
- Needs the two series aligned per date (UNION composite or a paired CALCULATE)
-

  ```dax
  Tracking Error =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR Sd = CALCULATE(
      STDEVX.P(
          VALUES(dim_date[Date]),
          VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
          VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
          RETURN IF(ISBLANK(Rp) || ISBLANK(Rb), BLANK(), Rp - Rb)
      ),
      Win
  )
  VAR N =
    CALCULATE(
        SUMX(
            VALUES(dim_date[Date]),
            VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
            VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
            RETURN IF(ISBLANK(Rp) || ISBLANK(Rb), BLANK(), 1)
        ),
        Win
    )
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  RETURN IF(N < 2, BLANK(), Sd * SQRT(DIVIDE(N, YearSpan)))
  ```

- Sd calculate stdev of Rp-Rb if they Rp and Rb both are not blank
- FirstD, LastD, YearSpan all same as before. Similar to volatility for Sd * SQRT(DIVIDE(N, YearSpan))

#### Information Ratio

- IR = annualized mean excess return ÷ annualized tracking error
- for every unit of deviation from the index, how much return did I actually earn?
- IR > 0.5 good sustained, ~1.0 excellent (rare), negative = you took on deviation and lost.
- IR is Sharpe pattern with the benchmark replacing the constant 4% risk-free
- Mean daily excess × (N/YearSpan), over the TE you already compute
-

  ```dax
  Information Ratio =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR MeanExcess =
    CALCULATE(
        AVERAGEX(
            VALUES(dim_date[Date]),
            VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
            VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
            RETURN IF(ISBLANK(Rp) || ISBLANK(Rb), BLANK(), Rp - Rb)
        ),
        Win
    )
  VAR N =
    CALCULATE(
        SUMX(
            VALUES(dim_date[Date]),
            VAR Rp = CALCULATE(AVERAGE(fact_snapshots[Time-Weight Return]))
            VAR Rb = CALCULATE(AVERAGE(fact_benchmark[DailyReturn]), fact_benchmark[Symbol] = "^GSPC")
            RETURN IF(ISBLANK(Rp) || ISBLANK(Rb), BLANK(), 1)
        ),
        Win
    )
  VAR FirstD = CALCULATE(MIN(fact_snapshots[Date]), Win)
  VAR LastD = CALCULATE(MAX(fact_snapshots[Date]), Win)
  VAR YearSpan = DIVIDE(DATEDIFF(FirstD, LastD, DAY), 365.25)
  VAR Te = [Tracking Error]
  RETURN IF(N < 2 || ISBLANK(Te) || Te = 0, BLANK(), DIVIDE(MeanExcess * DIVIDE(N, YearSpan), Te))
  ```

- Similar to Tracking Error, but find the mean excess returns

#### Expected Shortfall (CVaR 95%)

- Average of the days at or beyond your VaR boundary
-

  ```dax
  Expected Shortfall 95% =
  VAR Win = FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  VAR N = CALCULATE(COUNTA(fact_snapshots[Time-Weight Return]), Win)
  VAR Q = CALCULATE(
      PERCENTILEX.INC(fact_snapshots, fact_snapshots[Time-Weight Return], 0.05),
      Win
  )
  VAR Es = CALCULATE(
      AVERAGEX(
          fact_snapshots,
          VAR Rp = fact_snapshots[Time-Weight Return]
          RETURN IF(ISBLANK(Rp) || Rp > Q, BLANK(), Rp)
      ),
      Win
  )
  RETURN IF(N < 20 || ISBLANK(Es), BLANK(), Es)
```

#### Correlation heatmap

- Wanted to make a correlation between positions and the benchmarks
- To make it accurate, since my positions are not taken every single date, wanted to make sure they are accurate created additional python code to pull historical price action
- Added CSV, sort by symbol then date
- Group by Symbol to create another column
- Then created index column:

  ```dax
  Table.AddIndexColumn([AllData], "Index", 0, 1, Int64.Type)
  ```

- Remove previous group by symbols column
- Expand Indexed, Tick all but Symbol (already exists) to get all 1 date 1 symbol row with indexed 0-max for each symbol
- Add column : Prev_Index = [Index] + 1
- Merge the query with itself on Symbol + Prev_Index = Symbol + Index, expand Close as PrevClose.
- Add custom column DailyReturn = ([Close] / [Prev_Close]) - 1
-

  ```dax
  CurrentHoldings =
  VAR LastDay = CALCULATE(MAX(fact_positions[Date]), ALL(dim_symbol))
  RETURN
      CALCULATETABLE(
          fact_positions,
          fact_positions[Date] = LastDay
      )
  ```

- Created current holdings table
- Create Symbols A and B for the correlation heat map horizontal and vertical

  ```dax
  Symbols A = 
  UNION(
      DISTINCT(
          SELECTCOLUMNS(
              FILTER(
                  CurrentHoldings,
                  CurrentHoldings[Symbol] IN VALUES(fact_prices[Symbol])
              ),
              "Symbol", CurrentHoldings[Symbol]
          )
      ),
      ROW("Symbol", "^GSPC"),
      ROW("Symbol", "^IXIC")
  )
  ```

- Created Correlation Measure:

  ```dax
  Corr =
  VAR SymA = SELECTEDVALUE ( 'Symbols A'[Symbol] )
  VAR SymB = SELECTEDVALUE ( 'Symbols B'[Symbol] )
  VAR Win = FILTER ( ALL ( dim_date[Date] ), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End] )

  -- window means, one scalar per series (Beta pattern; unpaired is fine)
  VAR MeanA =
      IF (
          SymA IN VALUES ( fact_benchmark[Symbol] ),
          CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymA, Win ),
          CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymA, Win )
      )
  VAR MeanB =
      IF (
          SymB IN VALUES ( fact_benchmark[Symbol] ),
          CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymB, Win ),
          CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymB, Win )
      )

  -- Cov: per-date product of deviations, averaged over PAIRED dates only
  VAR Cov =
      CALCULATE (
          AVERAGEX (
              VALUES ( dim_date[Date] ),
              VAR Ra =
                  IF (
                      SymA IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymA ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymA )
                  )
              VAR Rb =
                  IF (
                      SymB IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymB ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymB )
                  )
              RETURN
                  IF ( ISBLANK ( Ra ) || ISBLANK ( Rb ), BLANK (), ( Ra - MeanA ) * ( Rb - MeanB ) )
          ),
          Win
      )

  -- SdA: per-date deviation of A, stdev over dates where A exists (regardless of B)
  VAR SdA =
      CALCULATE (
          STDEVX.P (
              VALUES ( dim_date[Date] ),
              VAR Ra =
                  IF (
                      SymA IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymA ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymA )
                  )
              RETURN IF ( ISBLANK ( Ra ), BLANK (), Ra - MeanA )
          ),
          Win
      )

  -- SdB: same as SdA, for B
  VAR SdB =
      CALCULATE (
          STDEVX.P (
              VALUES ( dim_date[Date] ),
              VAR Rb =
                  IF (
                      SymB IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymB ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymB )
                  )
              RETURN IF ( ISBLANK ( Rb ), BLANK (), Rb - MeanB )
          ),
          Win
      )

  -- PairedN: how many dates have BOTH series (this is what makes thin cells blank)
  VAR PairedN =
      CALCULATE (
          SUMX (
              VALUES ( dim_date[Date] ),
              VAR Ra =
                  IF (
                      SymA IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymA ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymA )
                  )
              VAR Rb =
                  IF (
                      SymB IN VALUES ( fact_benchmark[Symbol] ),
                      CALCULATE ( AVERAGE ( fact_benchmark[DailyReturn] ), fact_benchmark[Symbol] = SymB ),
                      CALCULATE ( AVERAGE ( fact_prices[DailyReturn] ), fact_prices[Symbol] = SymB )
                  )
              RETURN IF ( ISBLANK ( Ra ) || ISBLANK ( Rb ), BLANK (), 1 )
          ),
          Win
      )

  RETURN IF ( PairedN < 30, BLANK (), DIVIDE ( Cov, SdA * SdB ) )
  ```

- MeanA/MeanB - each series avg return over the window
- Cov - Covariance, walk through each date, get A and B return. If either missing, skip the date, otherwise ( Ra - MeanA ) * ( Rb - MeanB )
- SdA/SdB - stdev of each series deviations over the dates where the dates the series exist.
- PairedN - count 1 for every date where both exist. Dates where one symbol wasn't trading simply don't count.
- RETURN IF ( PairedN < 30, BLANK (), DIVIDE ( Cov, SdA * SdB ) ) -> Guard if less than 30 pairs. Divide Cov with product of SdA*Sdb
- Changed fact_price table data types so that they fit. Caused the error in the correlation matrix

#### Symbol Allocation Treemap

- Treemap on the Risks page: Symbol for the group, `Portfolio %` for the values — current holdings' weight share at a glance.

![Checkpoint 4 — Symbol Allocation Treemap](Media/Checkpoint%204%20-%20Symbol%20Allocation%20Treemap.png)

#### Daily Returns Histogram

  ```dax
  Return Count =
  CALCULATE(
      COUNTA(fact_snapshots[Time-Weight Return]),
      FILTER(ALL(dim_date[Date]), dim_date[Date] >= [WindowStart] && dim_date[Date] <= [Window End])
  )
  ```

- Bins: Data pane ▸ right-click fact_snapshots[Time-Weight Return] ▸ New group ▸ Bin type Number of bins is wrong here choose Size of bins ▸ size 0.02 (2% bins ≈ 20 bars over your −15% to +10% range). Name it e.g. Return Bin (2%).

- Visual: clustered column chart (not the histogram visual — that one can't use your windowed measure). X-axis = the new bin field (don't summarize), Y-axis = Return Count. Tooltip: add Time-Weight Return average if you want the exact mean per bar.

### Trades Page

#### Trades Ledger Table

- Table visual: Fields - dim_date[Date], fact_trades[Symbol], fact_trades[Name], fact_trades[Buy_Sell], fact_trades[Quantity], fact_trades[Fill_Price], fact_trades[Gross_Amount], fact_trades[Currency]
- Bind Date through dim_date
- Sort by Date descending, Format: percents n/a but money columns $ #,##0.00, remove gridlines, header text #C9CBD1, background #1A1A1F

---

## Phase 5 — Refresh & Delivery

> Status: DONE 1 Sep. Manual refresh loop proven; sources swapped to the Folder connector (zero hardcoded paths); PDF exported below as the delivery artifact.

- Reran the data pipeline, refreshed everything
- Redid the source file export using folders
- Replaced in the advanced editor the source paths
- Folder.Files("C:\Users\user\Hermes Workspace\Stock Market, Finance\Stock Portfolio project\powerbi\export"){[Name="dim_date.csv"]}[Content]

- Delivery: exported the full report to PDF

![Checkpoint 5 — Full report PDF export](Media/Stock%20Portfolio%20PowerBI%20pdf%20Export.pdf)

