"""Contract verification for the Power BI export (run from project root)."""
import pandas as pd
from pathlib import Path

EXP = Path("powerbi/export")
contract = {
    "dim_date": ["Date","Year","Quarter","QuarterLabel","Month","MonthName","Day","Weekday","WeekdayName","IsWeekend"],
    "dim_symbol": ["Symbol","AssetClass","IsOption","Underlying","Multiplier","Name","Market","Currency","Sector","Industry"],
    "fact_snapshots": ["Date","total_assets","stocks","options","cash","nav","units"],
    "fact_positions": ["Date","Symbol","Name","Market","Quantity","Market_Value","Diluted_Cost","Current_Price","P_L_Percent","P_L","Today_s_P_L","Currency","Portfolio_Percent"],
    "fact_cashflow": ["cashflow_id","Date","Currency","Type","in_out","Amount","Remark","is_external","is_income","CashflowCategory"],
    "fact_trades": ["Order_ID","date_time","Date","Symbol","Name","Market","Buy_Sell","Quantity","Fill_Price","Multiplier","Gross_Amount","Currency"],
    "fact_benchmark": ["Date","Symbol","Close"],
}

all_ok = True
for name, cols in contract.items():
    raw = (EXP / f"{name}.csv").read_bytes()
    bom = raw[:3] == b'\xef\xbb\xbf'
    df = pd.read_csv(EXP / f"{name}.csv")
    ok = list(df.columns) == cols
    all_ok = all_ok and bom and ok
    flag = "OK " if (bom and ok) else "FAIL"
    print(f"[{flag}] {name:16s} BOM={bom} cols_ok={ok} rows={len(df):5d}")
    if not ok:
        print("       GOT:", list(df.columns))

print()
fp = pd.read_csv(EXP / "fact_positions.csv")
print("Portfolio_Percent dtype:", fp["Portfolio_Percent"].dtype, "| sample:", fp["Portfolio_Percent"].iloc[0], "|", fp["Portfolio_Percent"].iloc[-1])
fc = pd.read_csv(EXP / "fact_cashflow.csv")
print("CashflowCategory values:", sorted(fc["CashflowCategory"].unique()))
print("cashflow Date range:", fc["Date"].iloc[0], "->", fc["Date"].iloc[-1])
fb = pd.read_csv(EXP / "fact_benchmark.csv")
print("benchmark min/max:", fb["Date"].min(), "/", fb["Date"].max(), "| symbols:", sorted(fb["Symbol"].unique()))
print("benchmark has pre-2026 rows:", int((fb["Date"] < "2026-01-01").sum()) > 0)
ds = pd.read_csv(EXP / "dim_symbol.csv")
n_stock = int((ds["AssetClass"] == "Stock").sum())
n_opt = int((ds["AssetClass"] == "Option").sum())
print(f"dim_symbol: stocks={n_stock} options={n_opt}")
blanks = int((ds["Sector"].isna() | (ds["Sector"] == "")).sum())
print("  blank sectors:", blanks, "| sample sectors:", sorted(ds["Sector"].dropna().unique())[:8])
opt_row = ds[ds["AssetClass"] == "Option"].iloc[0].to_dict()
print("  option row:", opt_row)
ft = pd.read_csv(EXP / "fact_trades.csv")
buy_ok = bool(((ft["Buy_Sell"] == "BUY") & (ft["Gross_Amount"] < 0)).all())
sell_ok = bool(((ft["Buy_Sell"] == "SELL") & (ft["Gross_Amount"] > 0)).all())
print("trades: BUY negative:", buy_ok, "| SELL positive:", sell_ok)
print("  SELL_SHORT gross:", ft[ft["Buy_Sell"] == "SELL_SHORT"]["Gross_Amount"].tolist()[:3], "| mult=100 rows:", int((ft["Multiplier"] == 100).sum()))
fd = pd.read_csv(EXP / "dim_date.csv")
print("dim_date:", len(fd), "rows |", fd["Date"].iloc[0], "->", fd["Date"].iloc[-1], "| Q label sample:", fd["QuarterLabel"].iloc[0])
print()
print("ALL CONTRACT CHECKS PASSED" if all_ok else "CONTRACT VIOLATIONS ABOVE")