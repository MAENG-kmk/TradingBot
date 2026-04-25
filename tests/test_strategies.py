# tests/test_strategies.py
import sys, os
sys.path.insert(0, os.path.abspath('.'))

import pytest
import pandas as pd
import numpy as np
import backtrader as bt

from backtestStrategy.DonchianStrategy import DonchianStrategy
from backtestStrategy.SupertrendStrategy import SupertrendStrategy
from backtestStrategy.EMACrossStrategy import EMACrossStrategy


def make_csv(tmp_path, n=400):
    """싸인파 추세 합성 4H 캔들 CSV 생성."""
    dates = pd.date_range('2022-01-01', periods=n, freq='4h')
    t = np.linspace(0, 6 * np.pi, n)
    base = np.linspace(30000, 50000, n)
    close = base + 5000 * np.sin(t) + np.random.default_rng(42).normal(0, 300, n)
    close = np.maximum(close, 1000)
    df = pd.DataFrame({
        'Date':   dates.strftime('%Y-%m-%d %H:%M:%S'),
        'Open':   close * 0.999,
        'High':   close * 1.006,
        'Low':    close * 0.994,
        'Close':  close,
        'Volume': np.random.default_rng(42).integers(1000, 9000, n).astype(float),
    })
    path = str(tmp_path / 'btc_test.csv')
    df.to_csv(path, index=False)
    return path


def _run(strategy_cls, csv_path, cash=10000.0):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls)
    data = bt.feeds.GenericCSVData(
        dataname=csv_path,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.0004)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    result = cerebro.run()
    strat = result[0]
    ta = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta, 'total') and hasattr(ta.total, 'total') else 0
    return total, cerebro.broker.getvalue()


# ── Donchian ──────────────────────────────────────────────────
def test_donchian_runs(tmp_path):
    _, final = _run(DonchianStrategy, make_csv(tmp_path))
    assert final > 0

def test_donchian_trades(tmp_path):
    total, _ = _run(DonchianStrategy, make_csv(tmp_path))
    assert total > 0, "DonchianStrategy must generate trades on trending data"

# ── Supertrend ────────────────────────────────────────────────
def test_supertrend_runs(tmp_path):
    _, final = _run(SupertrendStrategy, make_csv(tmp_path))
    assert final > 0

def test_supertrend_trades(tmp_path):
    total, _ = _run(SupertrendStrategy, make_csv(tmp_path))
    assert total > 0, "SupertrendStrategy must generate trades on trending data"

# ── EMA Cross ─────────────────────────────────────────────────
def test_emacross_runs(tmp_path):
    _, final = _run(EMACrossStrategy, make_csv(tmp_path))
    assert final > 0

def test_emacross_trades(tmp_path):
    total, _ = _run(EMACrossStrategy, make_csv(tmp_path))
    assert total > 0, "EMACrossStrategy must generate trades on trending data"
