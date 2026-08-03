"""Tests for the buy/sell audit ledger (#4) and date-stamped net P/L (#3).

Pure-logic tests only (no database, no network).
Run from the project root:  python -m pytest tests/ -q
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from source.db import option_multiplier, transaction_gross_amount


def test_option_multiplier_options():
    assert option_multiplier("NVDA270115C230000") == 100
    assert option_multiplier("SOFI260918C20000") == 100
    assert option_multiplier("GRAB270115C7500") == 100


def test_option_multiplier_stocks():
    assert option_multiplier("SOFI") == 1
    assert option_multiplier("AMZN") == 1
    assert option_multiplier("") == 1  # empty/None safe


def test_buy_is_negative_cash_out():
    # Stock: qty * price, negative (cash leaves the account).
    assert transaction_gross_amount("SOFI", "BUY", 25, 20.9) == -522.5


def test_sell_is_positive_cash_in():
    assert transaction_gross_amount("CHA", "SELL", 50, 11.17) == 558.5


def test_option_buy_uses_x100_multiplier():
    # Option: qty * price * 100, negative.
    assert transaction_gross_amount("NVDA270115C230000", "BUY", 1, 2.5) == -250.0


def test_option_sell_uses_x100_multiplier():
    assert transaction_gross_amount("AMZN260918C195000", "SELL", 1, 49.5) == 4950.0


def test_short_orders_are_treated_as_sells():
    # SELL_SHORT brings cash in (+); BUY_BACK takes cash out (-).
    assert transaction_gross_amount("TSLA", "SELL_SHORT", 3, 200) == 600.0
    assert transaction_gross_amount("TSLA", "BUY_BACK", 3, 205) == -615.0


def test_side_is_case_insensitive():
    assert transaction_gross_amount("AAPL", "buy", 1, 100) == -100.0
    assert transaction_gross_amount("AAPL", "SELL", 1, 110) == 110.0
