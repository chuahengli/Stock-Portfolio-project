"""Tests for cash-flow classification (dividend/income visibility in TWR) and
Time-Weighted Return inception handling.

These cover the pure logic only -- no network and no real database required.
Run from the project root:  python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd

# Ensure the project root is importable so `config` and `source` resolve.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from source.cleanup import classify_cashflow, cleanup_cashflow
from source.dashboard import get_twr


# --------------------------------------------------------------------------- #
# classify_cashflow
# --------------------------------------------------------------------------- #
def test_dividend_is_income_not_external():
    ext, inc = classify_cashflow("Cash Dividend", "V 8 SHARES DIVIDENDS 0.67 USD PER SHARE")
    assert ext is False
    assert inc is True


def test_dividend_tax_is_income_not_external():
    ext, inc = classify_cashflow("Dividend Tax", "V 8 SHARES WITHHOLDING TAX -0.20 USD - TAX")
    assert ext is False
    assert inc is True


def test_coupon_is_income_not_external():
    # Previously misclassified as external capital -- the core bug being fixed.
    ext, inc = classify_cashflow("Coupon", "Cash Voucher")
    assert ext is False
    assert inc is True


def test_others_coupon_deposit_is_income():
    ext, inc = classify_cashflow("Others", "Coupon Deposit")
    assert ext is False
    assert inc is True


def test_bank_transfer_is_external():
    ext, inc = classify_cashflow("Bank Transfer Withdrawals", "")
    assert ext is True
    assert inc is False


def test_paynow_deposit_is_external():
    ext, inc = classify_cashflow("Others", "PAYNOW2409040852519986389420240904085252")
    assert ext is True
    assert inc is False


def test_fund_subscription_is_neither():
    ext, inc = classify_cashflow("Others", "Fund Subscription#CSOP USD Money Market Fund")
    assert ext is False
    assert inc is False


def test_currency_exchange_is_neither():
    ext, inc = classify_cashflow("Currency Exchange", "")
    assert ext is False
    assert inc is False


def test_none_values_do_not_crash():
    ext, inc = classify_cashflow(None, None)
    assert ext is False
    assert inc is False


# --------------------------------------------------------------------------- #
# cleanup_cashflow end-to-end flagging
# --------------------------------------------------------------------------- #
def test_cleanup_cashflow_flags_rows():
    raw = pd.DataFrame({
        "cashflow_id":      [1, 2, 3, 4, 5, 6],
        "clearing_date":    ["2026-01-05"] * 6,
        "currency":         ["USD"] * 6,
        "cashflow_type":    ["Cash Dividend", "Dividend Tax", "Coupon",
                             "Bank Transfer Deposits", "Others", "Fund Subscription"],
        "cashflow_direction": ["IN", "OUT", "IN", "IN", "IN", "OUT"],
        "cashflow_amount":  [5.0, -1.5, 10.0, 100.0, 50.0, -200.0],
        "cashflow_remark":  ["V 8 SHARES DIVIDENDS 0.67", "WITHHOLDING TAX",
                             "Cash Voucher", "", "PAYNOW123456", "CSOP FUND SUBSCRIPTION"],
    })
    out = cleanup_cashflow(raw)

    assert list(out.columns) == [
        "cashflow_id", "Date", "Currency", "Type", "in_out", "Amount", "Remark",
        "is_external", "is_income",
    ]

    by_id = {int(r["cashflow_id"]): (r["is_external"], r["is_income"])
             for _, r in out.iterrows()}
    # Dividend + its tax -> income only
    assert by_id[1] == (0, 1)
    assert by_id[2] == (0, 1)
    # Cash voucher coupon -> income only (NOT external)
    assert by_id[3] == (0, 1)
    # Bank transfer -> external capital only
    assert by_id[4] == (1, 0)
    # PayNow deposit (Others) -> external only
    assert by_id[5] == (1, 0)
    # Fund subscription -> neither (wealth stays inside the account)
    assert by_id[6] == (0, 0)


def test_cleanup_cashflow_empty():
    out = cleanup_cashflow(pd.DataFrame())
    assert out.empty


# --------------------------------------------------------------------------- #
# get_twr inception handling
# --------------------------------------------------------------------------- #
def _twr_df():
    return pd.DataFrame({
        "date": ["2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"],
        # +10% , +10% , -10%
        "nav":  [100.0, 110.0, 121.0, 108.9],
    })


def test_twr_defaults_to_inception():
    # No dates passed -> uses earliest (inception) and latest snapshot.
    assert get_twr(_twr_df()) == "8.90%"


def test_twr_explicit_start_date():
    df = _twr_df()
    assert get_twr(df, pd.to_datetime("2026-01-13"), pd.to_datetime("2026-01-13")) == "0.00%"


def test_twr_matches_hardcoded_legacy_value():
    # The legacy hardcoded reference was the inception date (2026-01-12).
    df = _twr_df()
    legacy = get_twr(df, pd.to_datetime("2026-01-12"), pd.to_datetime("2026-01-15"))
    dynamic = get_twr(df, None, pd.to_datetime("2026-01-15"))
    assert legacy == dynamic == "8.90%"


def test_twr_empty_df():
    assert get_twr(pd.DataFrame()) == "N/A"
