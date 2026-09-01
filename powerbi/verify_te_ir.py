import csv, math
from datetime import date, datetime

def load_snapshots(path):
    rows = []
    with open(path, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            rows.append((datetime.strptime(r['Date'].strip(), '%Y-%m-%d').date(), float(r['nav'])))
    rows.sort()
    # TWR = nav/prev_nav - 1 (as in Power Query: [nav]/[Prev_Nav]-1)
    out = {}
    for i, (d, nav) in enumerate(rows):
        if i == 0:
            continue
        prev = rows[i-1][1]
        if prev == 0:
            continue
        out[d] = nav/prev - 1
    return rows, out

def load_benchmark(path, sym='^GSPC'):
    rows = []
    with open(path, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            if r['Symbol'].strip() != sym:
                continue
            close = r['Close'].strip()
            if not close:
                continue
            rows.append((datetime.strptime(r['Date'].strip(), '%Y-%m-%d').date(), float(close)))
    rows.sort()
    out = {}
    for i, (d, close) in enumerate(rows):
        if i == 0:
            continue
        prev = rows[i-1][1]
        out[d] = close/prev - 1
    return rows, out

def load_dates(path, key):
    ds = set()
    with open(path, encoding='utf-8-sig') as fh:
        rdr = csv.DictReader(fh)
        cols = rdr.fieldnames
        k = key if key in cols else cols[0]
        for r in rdr:
            ds.add(datetime.strptime(r[k].strip(), '%Y-%m-%d').date())
    return ds

# --- load ---
srows, twr = load_snapshots('fact_snapshots.csv')
brows, gspc = load_benchmark('fact_benchmark.csv')
dim_dates = load_dates('dim_date.csv', 'Date')
print(f"portfolio snapshots: {len(srows)} rows, {len(twr)} TWR dates; ^GSPC: {len(brows)} closes, {len(gspc)} daily returns; dim_date: {len(dim_dates)} dates")

anchor = max(r[0] for r in srows)       # Date Anchor = MAX(fact_snapshots[Date])
min_dim = min(dim_dates)
paired = sorted(set(twr) & set(gspc))   # dates where BOTH non-blank
print(f"anchor={anchor}, paired dates total = {len(paired)} (portfolio {len(twr)}, benchmark {len(gspc)})")

def edate(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def windows():
    return {
        'ALL': min_dim,
        '1Y': edate(anchor, -12),
        '6M': edate(anchor, -6),
        '3M': edate(anchor, -3),
        '1M': edate(anchor, -1),
        'YTD': date(anchor.year, 1, 1),
        '1W': anchor - timedelta(7),
    }
from datetime import timedelta

def analyze(wstart, wend=anchor):
    win_paired = [d for d in paired if wstart <= d <= wend]
    N = len(win_paired)
    if N < 2:
        return None
    # FirstD/LastD from PORTFOLIO side within window (DAX: MIN/MAX(fact_snapshots[Date]) under Win)
    win_snap_dates = [d for d, _ in srows if wstart <= d <= wend]
    FirstD = min(win_snap_dates); LastD = max(win_snap_dates)
    YS = (LastD - FirstD).days / 365.25
    diffs = [twr[d] - gspc[d] for d in win_paired]
    n = len(diffs)
    mean = sum(diffs)/n
    sd = math.sqrt(sum((x-mean)**2 for x in diffs)/n)          # STDEVX.P
    te = sd * math.sqrt(N/YS)
    ann_ex = mean * (N/YS)
    ir = ann_ex / te if te else float('nan')
    return dict(N=N, FirstD=FirstD, LastD=LastD, YS=round(YS,4), mean_d=mean, sd=sd,
                TE=te, ann_ex=ann_ex, IR=ir, vol_p=None)

print(f"\n{'Win':<5}{'N':>4}{'FirstD':>12}{'LastD':>12}{'YS':>8}{'meanEx':>10}{'Sd':>10}{'TE%':>9}{'annEx%':>10}{'IR':>8}")
for label, ws in windows().items():
    r = analyze(ws)
    if r is None:
        print(f"{label:<5}{'<2':>4}  (blank)")
        continue
    print(f"{label:<5}{r['N']:>4}{str(r['FirstD']):>12}{str(r['LastD']):>12}{r['YS']:>8}{r['mean_d']*100:>10.4f}{r['sd']*100:>10.4f}{r['TE']*100:>9.2f}{r['ann_ex']*100:>10.2f}{r['IR']:>8.2f}")

# Portfolio vol (ALL) for the TE < vol QA tell
import statistics
rall = analyze(min_dim)
# Shipped Portfolio Volatility iterates fact_snapshots directly (ALL portfolio returns), not paired:
all_dates = sorted(twr.keys())
pmean = sum(twr[d] for d in all_dates)/len(all_dates)
pvol_sd = math.sqrt(sum((twr[d]-pmean)**2 for d in all_dates)/len(all_dates))
ys = (max(srows)[0] - min(srows)[0]).days/365.25
ann_pvol = pvol_sd * math.sqrt(len(all_dates)/ys)
print(f"\nPortfolio daily sd(all paired dates)={pvol_sd*100:.4f}%, ann vol≈{ann_pvol*100:.2f}% (TE {rall['TE']*100:.2f}% < {ann_pvol*100:.2f}% ? {rall['TE'] < ann_pvol})")
