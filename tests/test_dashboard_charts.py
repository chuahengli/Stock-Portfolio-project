"""Regression tests for the dashboard classification charts.

Pure logic: no DB, no network. These encode the two bugs that made the
Geography and Market Cap panes render blank, plus the no-network invariant.
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

from source import dashboard


def _pos(countries, caps, sectors=None):
    n = len(countries)
    return pd.DataFrame({
        "Ticker": [f"T{i}" for i in range(n)],
        "Sector": sectors or ["Technology"] * n,
        "Country": countries,
        "Market_Cap_Cat": caps,
        "Sort_Val": [10.0 / n] * n,
    })


def test_no_yfinance_calls_in_render_path():
    """The 10s render loop must never hit yfinance -- that produced the
    401/429 storms and blanked the charts."""
    src = Path(dashboard.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if fn.value.id == "yf":
                    pytest.fail("dashboard still calls yfinance")
    assert "import yfinance" not in src
    assert "fast_info" not in src.replace("# fast_info", "")


def test_geo_and_marketcap_panes_never_empty():
    """NaN Country (old get_country failure) and all-'Unknown' market caps must
    still produce bars in BOTH panes."""
    dead = _pos([None, float("nan"), None], ["Unknown"] * 3)
    fig = dashboard.plot_portfolio_characteristics(dead)
    by_name = {tr.name: tr for tr in fig.data}
    assert len(by_name["Geography"].x) > 0, "Geography pane blank"
    assert len(by_name["Market Cap"].x) > 0, "Market Cap pane blank"


def test_xaxis_ranges_are_finite():
    """An empty group must not leave a NaN x-axis range."""
    import numpy as np
    dead = _pos([None], ["Unknown"])
    fig = dashboard.plot_portfolio_characteristics(dead)
    for ax in ("xaxis", "xaxis2", "xaxis3"):
        rng = getattr(fig.layout, ax).range
        assert rng is not None
        assert all(v is not None and np.isfinite(v) for v in rng), (ax, rng)


def test_market_cap_class_handles_bad_input():
    """get_mktcap had no try/except; a 401 used to propagate and kill Overview."""
    assert dashboard.market_cap_class(None) == "Unknown"
    assert dashboard.market_cap_class(float("nan")) == "Unknown"
    assert dashboard.market_cap_class("n/a") == "Unknown"
    assert dashboard.market_cap_class(0) == "Unknown"
    assert dashboard.market_cap_class(5e11) == "Mega"
    assert dashboard.market_cap_class(5e10) == "Large"
    assert dashboard.market_cap_class(5e9) == "Mid"
    assert dashboard.market_cap_class(5e8) == "Small"
    assert dashboard.market_cap_class(1e8) == "Micro"
    assert dashboard.market_cap_class(1e6) == "Nano"


def test_unknown_country_is_a_visible_bucket():
    live = _pos(["United States", None], ["Large", "Unknown"])
    fig = dashboard.plot_portfolio_characteristics(live)
    geo = {tr.name: tr for tr in fig.data}["Geography"]
    assert "Unknown" in list(geo.y)
    assert len(geo.x) == 2
