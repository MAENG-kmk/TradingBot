# BTC 4H 추세추종 전략 비교 백테스트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BTC/USDT 4H 캔들 기준으로 Donchian, Supertrend, EMA Cross 세 전략을 동일 조건으로 백테스트하고 결과를 비교한다.

**Architecture:** backtrader 기반으로 각 전략을 독립 파일로 구현하고, `backtest_compare_btc.py`가 세 전략을 순차 실행해 비교 표와 에쿼티 커브를 출력한다. 데이터는 ccxt로 2020-01-01~현재를 fetch해 CSV 캐싱한다.

**Tech Stack:** Python 3.10, backtrader, ccxt, pandas, numpy, matplotlib, pytest

---

## 파일 구조

```
backtestDatas/
  btcusdt_4h_compare.csv     # Task 1에서 생성 (2020-01-01~현재)

backtestStrategy/
  DonchianStrategy.py        # Task 3 — 전략 A
  SupertrendStrategy.py      # Task 4 — 전략 B
  EMACrossStrategy.py        # Task 5 — 전략 C

tests/
  test_strategies.py         # Task 2 — 세 전략 smoke test

backtest_compare_btc.py      # Task 6 — 비교 실행 스크립트
```

---

## Task 1: BTC 4H 데이터 준비 (2020-01-01 ~ 현재)

**Files:**
- Create: `fetch_btc_data.py` (임시 스크립트, 실행 후 삭제해도 됨)
- Create: `backtestDatas/btcusdt_4h_compare.csv`

- [ ] **Step 1: ccxt 설치 확인**

```bash
pip install ccxt
```

- [ ] **Step 2: fetch_btc_data.py 작성**

```python
# fetch_btc_data.py
import ccxt
import pandas as pd
import time
from datetime import datetime

def fetch_btc_4h(save_path='backtestDatas/btcusdt_4h_compare.csv'):
    exchange = ccxt.binance({'enableRateLimit': True})
    since = exchange.parse8601('2020-01-01T00:00:00Z')
    all_ohlcv = []

    while True:
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '4h', since=since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        last_ts = ohlcv[-1][0]
        print(f"  fetched to {datetime.utcfromtimestamp(last_ts/1000)}, total: {len(all_ohlcv)}")
        since = last_ts + 1
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if last_ts >= now_ms - 4 * 3600 * 1000:
            break
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(all_ohlcv, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['Date'] = pd.to_datetime(df['Date'], unit='ms').dt.strftime('%Y-%m-%d %H:%M:%S')
    df.to_csv(save_path, index=False)
    print(f"Saved {len(df)} rows → {save_path}")
    print(f"Range: {df['Date'].iloc[0]}  ~  {df['Date'].iloc[-1]}")

if __name__ == '__main__':
    fetch_btc_4h()
```

- [ ] **Step 3: 실행**

```bash
python fetch_btc_data.py
```

Expected output:
```
fetched to 2020-04-10 ..., total: 1000
...
Saved ~13000 rows → backtestDatas/btcusdt_4h_compare.csv
Range: 2020-01-01 00:00:00  ~  2026-04-xx xx:xx:xx
```

- [ ] **Step 4: 데이터 검증**

```bash
python -c "
import pandas as pd
df = pd.read_csv('backtestDatas/btcusdt_4h_compare.csv')
print(f'rows: {len(df)}')
print(f'first: {df[\"Date\"].iloc[0]}')
print(f'last:  {df[\"Date\"].iloc[-1]}')
print(df.dtypes)
"
```

Expected: rows > 12000, first ≈ 2020-01-01, last ≈ 오늘

- [ ] **Step 5: Commit**

```bash
git add backtestDatas/btcusdt_4h_compare.csv
git commit -m "data: BTC/USDT 4H 비교용 데이터 2020-01-01~현재"
```

---

## Task 2: 테스트 스캐폴드 작성

**Files:**
- Create: `tests/test_strategies.py`

- [ ] **Step 1: test_strategies.py 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인 (ImportError 예상)**

```bash
python -m pytest tests/test_strategies.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` (전략 파일 없으므로)

---

## Task 3: DonchianStrategy 구현

**Files:**
- Create: `backtestStrategy/DonchianStrategy.py`

- [ ] **Step 1: DonchianStrategy.py 작성**

```python
# backtestStrategy/DonchianStrategy.py
import backtrader as bt


class DonchianStrategy(bt.Strategy):
    """
    Donchian Channel Breakout — 롱/숏 양방향
    진입: N봉 최고가/최저가 돌파
    청산: M봉 반대 채널 돌파 또는 ATR 손절
    """
    params = dict(
        entry_period=20,
        exit_period=10,
        atr_period=14,
        atr_stop_mult=2.0,
    )

    def __init__(self):
        high = self.data.high
        low  = self.data.low

        self.entry_high = bt.ind.Highest(high, period=self.p.entry_period)
        self.entry_low  = bt.ind.Lowest(low,   period=self.p.entry_period)
        self.exit_high  = bt.ind.Highest(high, period=self.p.exit_period)
        self.exit_low   = bt.ind.Lowest(low,   period=self.p.exit_period)
        self.atr        = bt.ind.ATR(self.data, period=self.p.atr_period)

        self._side       = None
        self._stop_price = None

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def _enter_long(self):
        size = self._full_size()
        self.buy(size=size)
        self._side       = 'long'
        self._stop_price = self.data.close[0] - self.atr[0] * self.p.atr_stop_mult

    def _enter_short(self):
        size = self._full_size()
        self.sell(size=size)
        self._side       = 'short'
        self._stop_price = self.data.close[0] + self.atr[0] * self.p.atr_stop_mult

    def next(self):
        price = self.data.close[0]

        if not self.position:
            # entry_high/low[-1] = 전봉 기준 N봉 최고/최저 (lookahead 방지)
            if price > self.entry_high[-1]:
                self._enter_long()
            elif price < self.entry_low[-1]:
                self._enter_short()
            return

        if self._side == 'long':
            if price < self.exit_low[-1] or price < self._stop_price:
                self.close()
                self._side = None
                if price < self.entry_low[-1]:
                    self._enter_short()
        elif self._side == 'short':
            if price > self.exit_high[-1] or price > self._stop_price:
                self.close()
                self._side = None
                if price > self.entry_high[-1]:
                    self._enter_long()
```

- [ ] **Step 2: Donchian 테스트 실행**

```bash
python -m pytest tests/test_strategies.py::test_donchian_runs tests/test_strategies.py::test_donchian_trades -v
```

Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add backtestStrategy/DonchianStrategy.py tests/test_strategies.py
git commit -m "feat: DonchianStrategy 롱/숏 양방향 추세추종 구현"
```

---

## Task 4: SupertrendStrategy 구현

**Files:**
- Create: `backtestStrategy/SupertrendStrategy.py`

- [ ] **Step 1: SupertrendStrategy.py 작성**

```python
# backtestStrategy/SupertrendStrategy.py
import backtrader as bt


class _SupertrendIndicator(bt.Indicator):
    """ATR 기반 Supertrend 인디케이터."""
    lines = ('supertrend', 'direction',)
    params = dict(period=10, multiplier=3.0)

    def __init__(self):
        self.atr = bt.ind.ATR(self.data, period=self.p.period)
        self._fu = None  # final upper
        self._fl = None  # final lower

    def next(self):
        hl2         = (self.data.high[0] + self.data.low[0]) / 2.0
        atr         = self.atr[0]
        basic_upper = hl2 + self.p.multiplier * atr
        basic_lower = hl2 - self.p.multiplier * atr

        if self._fu is None:
            self._fu = basic_upper
            self._fl = basic_lower
            self.lines.direction[0]  = 1.0
            self.lines.supertrend[0] = basic_lower
            return

        prev_close = self.data.close[-1]
        self._fu = basic_upper if (basic_upper < self._fu or prev_close > self._fu) else self._fu
        self._fl = basic_lower if (basic_lower > self._fl or prev_close < self._fl) else self._fl

        prev_dir = self.lines.direction[-1]
        if prev_dir == -1.0 and self.data.close[0] > self._fu:
            direction = 1.0
        elif prev_dir == 1.0 and self.data.close[0] < self._fl:
            direction = -1.0
        else:
            direction = prev_dir

        self.lines.direction[0]  = direction
        self.lines.supertrend[0] = self._fl if direction == 1.0 else self._fu


class SupertrendStrategy(bt.Strategy):
    """
    Supertrend 추세추종 — 롱/숏 양방향
    방향 전환 시 즉시 포지션 반전
    """
    params = dict(
        st_period=10,
        st_multiplier=3.0,
    )

    def __init__(self):
        self.st = _SupertrendIndicator(
            self.data,
            period=self.p.st_period,
            multiplier=self.p.st_multiplier,
        )
        self._side = None

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def next(self):
        direction     = self.st.lines.direction[0]
        prev_direction = self.st.lines.direction[-1]

        # 방향 전환 감지
        turned_up   = (prev_direction == -1.0 and direction == 1.0)
        turned_down = (prev_direction ==  1.0 and direction == -1.0)

        if not self.position:
            if turned_up:
                self.buy(size=self._full_size())
                self._side = 'long'
            elif turned_down:
                self.sell(size=self._full_size())
                self._side = 'short'
        else:
            if self._side == 'long' and turned_down:
                self.close()
                self._side = None
                self.sell(size=self._full_size())
                self._side = 'short'
            elif self._side == 'short' and turned_up:
                self.close()
                self._side = None
                self.buy(size=self._full_size())
                self._side = 'long'
```

- [ ] **Step 2: Supertrend 테스트 실행**

```bash
python -m pytest tests/test_strategies.py::test_supertrend_runs tests/test_strategies.py::test_supertrend_trades -v
```

Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add backtestStrategy/SupertrendStrategy.py
git commit -m "feat: SupertrendStrategy ATR 기반 추세추종 구현"
```

---

## Task 5: EMACrossStrategy 구현

**Files:**
- Create: `backtestStrategy/EMACrossStrategy.py`

- [ ] **Step 1: EMACrossStrategy.py 작성**

```python
# backtestStrategy/EMACrossStrategy.py
import backtrader as bt


class EMACrossStrategy(bt.Strategy):
    """
    EMA 골든/데드크로스 진입 + ATR 트레일링 스탑 청산 — 롱/숏 양방향
    """
    params = dict(
        fast=9,
        slow=21,
        atr_period=14,
        trail_mult=3.0,
    )

    def __init__(self):
        self.ema_fast   = bt.ind.EMA(self.data.close, period=self.p.fast)
        self.ema_slow   = bt.ind.EMA(self.data.close, period=self.p.slow)
        self.cross_up   = bt.ind.CrossUp(self.ema_fast,   self.ema_slow)
        self.cross_down = bt.ind.CrossDown(self.ema_fast, self.ema_slow)
        self.atr        = bt.ind.ATR(self.data, period=self.p.atr_period)

        self._side        = None
        self._trail_stop  = None
        self._extreme     = None  # long: 최고가 / short: 최저가

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def _update_trail(self, price):
        if self._side == 'long':
            if price > self._extreme:
                self._extreme    = price
                self._trail_stop = self._extreme - self.atr[0] * self.p.trail_mult
        elif self._side == 'short':
            if price < self._extreme:
                self._extreme    = price
                self._trail_stop = self._extreme + self.atr[0] * self.p.trail_mult

    def next(self):
        price = self.data.close[0]

        if not self.position:
            if self.cross_up[0]:
                self.buy(size=self._full_size())
                self._side       = 'long'
                self._extreme    = price
                self._trail_stop = price - self.atr[0] * self.p.trail_mult
            elif self.cross_down[0]:
                self.sell(size=self._full_size())
                self._side       = 'short'
                self._extreme    = price
                self._trail_stop = price + self.atr[0] * self.p.trail_mult
            return

        self._update_trail(price)

        if self._side == 'long' and price < self._trail_stop:
            self.close()
            self._side = None
            if self.cross_down[0]:
                self.sell(size=self._full_size())
                self._side       = 'short'
                self._extreme    = price
                self._trail_stop = price + self.atr[0] * self.p.trail_mult

        elif self._side == 'short' and price > self._trail_stop:
            self.close()
            self._side = None
            if self.cross_up[0]:
                self.buy(size=self._full_size())
                self._side       = 'long'
                self._extreme    = price
                self._trail_stop = price - self.atr[0] * self.p.trail_mult
```

- [ ] **Step 2: 전체 테스트 실행 — 6개 통과 확인**

```bash
python -m pytest tests/test_strategies.py -v
```

Expected:
```
test_donchian_runs    PASSED
test_donchian_trades  PASSED
test_supertrend_runs  PASSED
test_supertrend_trades PASSED
test_emacross_runs    PASSED
test_emacross_trades  PASSED
6 passed
```

- [ ] **Step 3: Commit**

```bash
git add backtestStrategy/EMACrossStrategy.py
git commit -m "feat: EMACrossStrategy EMA크로스+ATR트레일링 추세추종 구현"
```

---

## Task 6: 비교 실행 스크립트 구현

**Files:**
- Create: `backtest_compare_btc.py`

- [ ] **Step 1: backtest_compare_btc.py 작성**

```python
# backtest_compare_btc.py
"""
BTC 4H 추세추종 전략 비교 백테스트
실행: python backtest_compare_btc.py
      python backtest_compare_btc.py --plot
      python backtest_compare_btc.py --save
"""
import argparse
import os
import sys
sys.path.append(os.path.abspath('.'))

import numpy as np
import pandas as pd
import backtrader as bt

from backtestStrategy.DonchianStrategy   import DonchianStrategy
from backtestStrategy.SupertrendStrategy import SupertrendStrategy
from backtestStrategy.EMACrossStrategy   import EMACrossStrategy

DATA_PATH    = 'backtestDatas/btcusdt_4h_compare.csv'
INITIAL_CASH = 10_000.0
COMMISSION   = 0.0004   # 0.04% taker fee
SLIPPAGE     = 0.0002   # 0.02%

STRATEGIES = [
    ('Donchian',    DonchianStrategy,   {}),
    ('Supertrend',  SupertrendStrategy, {}),
    ('EMA Cross',   EMACrossStrategy,   {}),
]


class _EquityCurve(bt.Analyzer):
    def start(self):
        self._dates  = []
        self._values = []

    def next(self):
        self._dates.append(self.strategy.data.datetime.date(0))
        self._values.append(self.strategy.broker.getvalue())

    def get_analysis(self):
        return {'dates': self._dates, 'values': self._values}


def _load_feed():
    return bt.feeds.GenericCSVData(
        dataname=DATA_PATH,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
    )


def run_one(name, strategy_cls, params):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls, **params)
    cerebro.adddata(_load_feed())
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.broker.set_slippage_perc(
        perc=SLIPPAGE, slip_open=True, slip_limit=True,
        slip_match=True, slip_out=False,
    )
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name='sharpe',
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(_EquityCurve,               _name='equity')

    result = cerebro.run()
    strat  = result[0]

    ta      = strat.analyzers.trades.get_analysis()
    total   = ta.total.total if hasattr(ta.total, 'total') else 0
    won     = ta.won.total   if (total > 0 and hasattr(ta, 'won'))  else 0
    lost    = ta.lost.total  if (total > 0 and hasattr(ta, 'lost')) else 0
    avg_p   = ta.won.pnl.average  if won  > 0 else 0.0
    avg_l   = ta.lost.pnl.average if lost > 0 else 0.0

    final   = cerebro.broker.getvalue()
    ror     = (final - INITIAL_CASH) / INITIAL_CASH * 100
    sharpe  = strat.analyzers.sharpe.get_analysis().get('sharperatio') or 0.0
    mdd     = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0)
    pl      = abs(avg_p / avg_l) if avg_l != 0 else 0.0
    eq      = strat.analyzers.equity.get_analysis()

    return {
        'name':      name,
        'trades':    total,
        'win_rate':  won / total * 100 if total > 0 else 0.0,
        'pl_ratio':  pl,
        'ror':       ror,
        'sharpe':    sharpe,
        'mdd':       mdd,
        'final':     final,
        'equity':    eq,
    }


def print_table(results):
    header = f"{'전략':<14} {'총수익률':>9} {'Sharpe':>7} {'MDD':>7} {'승률':>7} {'손익비':>7} {'거래':>6}"
    print('\n' + '=' * len(header))
    print(header)
    print('-' * len(header))
    for r in results:
        print(
            f"{r['name']:<14} "
            f"{r['ror']:>8.1f}%  "
            f"{r['sharpe']:>6.2f}  "
            f"{r['mdd']:>6.1f}%  "
            f"{r['win_rate']:>6.1f}%  "
            f"{r['pl_ratio']:>6.2f}  "
            f"{r['trades']:>5}"
        )
    print('=' * len(header))


def plot_equity(results, save_path=None):
    import matplotlib
    if save_path:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    colors = ['#00b4d8', '#26a69a', '#ffa726']
    fig, ax = plt.subplots(figsize=(14, 6), facecolor='#1e1e1e')
    ax.set_facecolor('#2b2b2b')

    for r, color in zip(results, colors):
        eq     = r['equity']
        dates  = pd.to_datetime(eq['dates'])
        values = np.array(eq['values'])
        ax.plot(dates, values / INITIAL_CASH * 100, color=color,
                linewidth=1.5, label=f"{r['name']} ({r['ror']:+.1f}%)")

    ax.axhline(y=100, color='#555', linestyle=':', linewidth=0.8)
    ax.set_ylabel('Portfolio Value (%)', color='#ccc')
    ax.set_title('BTC 4H Trend-Following Strategy Comparison', color='white', fontsize=13)
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values():
        sp.set_color('#444')
    ax.legend(facecolor='#333', labelcolor='white', fontsize=10)

    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='#1e1e1e')
        print(f"차트 저장: {save_path}")
    else:
        plt.tight_layout()
        plt.show()
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BTC 4H 추세추종 전략 비교')
    parser.add_argument('--plot', action='store_true', help='에쿼티 커브 화면 출력')
    parser.add_argument('--save', action='store_true', help='에쿼티 커브 PNG 저장')
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"데이터 없음: {DATA_PATH}\npython fetch_btc_data.py 를 먼저 실행하세요.")
        sys.exit(1)

    results = []
    for name, cls, params in STRATEGIES:
        print(f"[{name}] 실행 중...")
        r = run_one(name, cls, params)
        results.append(r)
        print(f"  완료 — ROR: {r['ror']:+.1f}%  Sharpe: {r['sharpe']:.2f}  MDD: {r['mdd']:.1f}%")

    print_table(results)

    if args.plot:
        plot_equity(results)
    elif args.save:
        plot_equity(results, save_path='charts/btc_compare.png')
```

- [ ] **Step 2: Commit**

```bash
git add backtest_compare_btc.py
git commit -m "feat: BTC 4H 추세추종 전략 비교 실행 스크립트 구현"
```

---

## Task 7: 백테스트 실행 및 결과 확인

- [ ] **Step 1: 전체 테스트 최종 확인**

```bash
python -m pytest tests/test_strategies.py -v
```

Expected: 6 passed

- [ ] **Step 2: 백테스트 실행**

```bash
python backtest_compare_btc.py
```

Expected (수치는 실행마다 다름):
```
[Donchian] 실행 중...
  완료 — ROR: +xxx%  Sharpe: x.xx  MDD: xx.x%
[Supertrend] 실행 중...
  완료 — ROR: +xxx%  Sharpe: x.xx  MDD: xx.x%
[EMA Cross] 실행 중...
  완료 — ROR: +xxx%  Sharpe: x.xx  MDD: xx.x%

==============================================
전략           총수익률   Sharpe     MDD    승률   손익비   거래
----------------------------------------------
Donchian       +xxx.x%    x.xx   xx.x%  xx.x%   x.xx    xx
Supertrend     +xxx.x%    x.xx   xx.x%  xx.x%   x.xx    xx
EMA Cross      +xxx.x%    x.xx   xx.x%  xx.x%   x.xx    xx
==============================================
```

- [ ] **Step 3: 에쿼티 커브 저장**

```bash
python backtest_compare_btc.py --save
```

Expected: `charts/btc_compare.png` 생성

- [ ] **Step 4: 최종 Commit**

```bash
git add charts/btc_compare.png
git commit -m "result: BTC 4H 추세추종 비교 백테스트 에쿼티 커브"
```
