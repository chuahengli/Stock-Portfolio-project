# Power BI Learning Notes

My own record of what I did, what surprised me, and what I decided.
Written in my own words.

Screenshots live in `Media/` and are linked from here.

How I use this file: at each checkpoint, fill the matching section before moving on.

## Conventions

- Screenshots: `Media/Checkpoint N - <topic>.png`, linked below.

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

#### Sharpe Ratio

#### Tracking Error (skeleton)

- Question it answers: "how different am I actually from the index?"
- Inputs: daily portfolio return (fact_snapshots[Time-Weight Return]), daily benchmark return (fact_benchmark[DailyReturn], one Symbol — likely ^GSPC)
- Pattern: same skeleton as the vol measures — Win filter, N, FirstD/LastD, YearSpan — but the stdev runs over the daily difference, not the raw return
- Needs the two series aligned per date (UNION composite or a paired CALCULATE); benchmark has no dim_symbol row — pin the Symbol, don't average
- Format: "0.0%", blank guard when N < 2
- QA: ALL window → small number if the portfolio broadly tracks ^GSPC; window to 1M → jumps around

#### Top-5 Weight / Concentration (skeleton)

- Question it answers: "is the risk really just a few names?"
- Inputs: fact_positions latest as-of weights (reuse the as-of allocation pattern: LastDataDay pinned per the dim filter pitfall, ALL(dim_symbol) in the denominator)
- Measure: MAXX over the top 5 symbol weights after as-of (or a top-N bar visual + a single "Top-5 combined weight" card)
- USD-basis caveat applies (SGD leftovers unconverted)
- QA: sum of the 5 bars against the card value

#### Historical VaR at 5% (skeleton)

- Question it answers: "on a bad day, how bad?"
- Inputs: fact_snapshots[Time-Weight Return] within Win
- Pattern: PERCENTILEX.INC over the windowed returns at 0.05; window wrapper + blank guard like the vol measures
- Format: "0.0%"; label should say the confidence level so the card is self-explanatory
- QA: compare against eyeballing the worst daily returns on the Overview line for the same window

#### Calmar Ratio (skeleton)

- Question it answers: return per unit of worst pain (no risk-free rate needed)
- Inputs: CAGR (may not exist yet as a measure) and [Max Drawdown]
- Pattern: one DIVIDE, guard on the denominator (drawdown is negative — decide DIVIDE(..., -[Max Drawdown]) or ABS)
- QA: ALL window over the full history; a positive-return portfolio must print positive

#### Recovery Time (skeleton)

- Question it answers: how long the worst dip took to heal
- Inputs: Drawdown calculated table (Level, PeakSoFar per Date)
- Pattern: find the date of [Max Drawdown] (the trough), then MINX over dates after the trough where Level returns to the trough's PeakSoFar
- Optional visual: card in days, or annotate the drawdown line
- QA: pick a known dip in the line and count days by hand for one window

---

## Phase 5 — Refresh & Delivery

_(empty until reached)_
