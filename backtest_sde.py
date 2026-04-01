"""
SDE 전략 종합 백테스트
  1. 레버리지 스윕  (4h 데이터, leverage: 1x / 2x / 3x / 5x / 10x)
  2. 타임프레임 비교 (1x 레버리지, 4h / 1h)

레버리지 시뮬레이션:
  backtrader 의 commission mult 를 leverage 배수로 설정.
  → 동일한 포지션 크기에서 P&L 이 leverage 배 증폭됨
  → 동일 자본으로 leverage 배 규모를 운용하는 것과 수익률 동일.
  청산선 = 진입가 × (1 - 0.9/leverage) — 하드스탑(stop_ror=2%)이 항상 먼저 발동되므로
  leverage ≤ 45 범위에서 강제 청산 없음.

사용법:
  python backtest_sde.py
"""

import sys
import os
sys.path.append(os.path.abspath("."))

import pandas as pd
import backtrader as bt
from backtestStrategy.SDEStrategy import SDEStrategy


def _load_intrabar(symbol):
    path = f'backtestDatas/{symbol.lower()}usdt_1h.csv'
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df

_BTC_1H = _load_intrabar('btc')

# ── 공통 최적 파라미터 ─────────────────────────────────────────────
BASE_PARAMS = dict(
    target_ror=0.04,
    stop_ror=0.02,
    entry_prob=0.58,
    exit_prob=0.35,
    risk_percent=0.02,
)
INITIAL_CASH = 100_000.0


def run_one(data_path, compression, est_window, max_bars, leverage, params):
    """단일 조건 백테스트 실행, 결과 dict 반환"""
    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        SDEStrategy,
        est_window=est_window,
        max_bars=max_bars,
        leverage=leverage,
        intrabar_data=_BTC_1H,
        **params,
    )

    feed = bt.feeds.GenericCSVData(
        dataname=data_path,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=compression,
        openinterest=-1,
        headers=True,
    )
    cerebro.adddata(feed)
    cerebro.broker.setcash(INITIAL_CASH)

    # leverage 를 mult 로 설정 → P&L 을 leverage 배 증폭
    cerebro.broker.setcommission(commission=0.0005, mult=float(leverage))

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name='sharpe',
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    result = cerebro.run()
    strat  = result[0]

    ta    = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0

    if total == 0:
        return None

    won   = ta.won.total
    lost  = ta.lost.total
    avg_p = ta.won.pnl.average  if won  > 0 else 0.0
    avg_l = ta.lost.pnl.average if lost > 0 else 0.0
    final = cerebro.broker.getvalue()
    ror   = (final - INITIAL_CASH) / INITIAL_CASH * 100
    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio') or 0.0
    mdd    = strat.analyzers.drawdown.get_analysis() \
                 .get('max', {'drawdown': 0})['drawdown']
    pl     = abs(avg_p / avg_l) if avg_l != 0 else 0.0

    return {
        'trades': total, 'won': won, 'lost': lost,
        'win_rate': won / total * 100,
        'pl_ratio': pl, 'ror': ror, 'sharpe': sharpe, 'mdd': mdd,
    }


def print_table(title, rows, col_headers, row_labels):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    fmt_h = f"  {'':12s}" + "".join(f"{h:>10s}" for h in col_headers)
    print(fmt_h)
    print(f"  {'-'*68}")
    for label, row in zip(row_labels, rows):
        if row is None:
            print(f"  {label:<12s}   거래 없음")
            continue
        vals = (
            f"{row['ror']:>+9.1f}%",
            f"{row['sharpe']:>9.2f}",
            f"{row['mdd']:>9.1f}%",
            f"{row['win_rate']:>9.1f}%",
            f"{row['pl_ratio']:>9.2f}",
            f"{row['trades']:>9d}",
        )
        print(f"  {label:<12s}" + "".join(vals))
    print(f"{'='*70}")


# ══════════════════════════════════════════════════════════════════════
#  1. 레버리지 스윕 — 4h 데이터
# ══════════════════════════════════════════════════════════════════════
print("\n▶ 레버리지 스윕 실행 중... (4h 데이터)")

leverage_levels = [1, 2, 3, 5, 10]
lev_results = []

for lev in leverage_levels:
    print(f"  leverage={lev}x ...", end=" ", flush=True)
    r = run_one(
        data_path   = 'backtestDatas/btcusdt_4h.csv',
        compression = 240,
        est_window  = 50,
        max_bars    = 48,
        leverage    = lev,
        params      = BASE_PARAMS,
    )
    lev_results.append(r)
    if r:
        print(f"ROR={r['ror']:+.1f}%  MDD={r['mdd']:.1f}%  Sharpe={r['sharpe']:.2f}")
    else:
        print("거래 없음")

print_table(
    title       = "레버리지별 성과 (BTC 4h, 초기자본 $100,000)",
    rows        = lev_results,
    col_headers = ["ROR", "Sharpe", "MDD", "승률", "P/L비", "거래수"],
    row_labels  = [f"{l}x" for l in leverage_levels],
)

# ══════════════════════════════════════════════════════════════════════
#  2. 타임프레임 비교 — 1x 레버리지
# ══════════════════════════════════════════════════════════════════════
print("\n\n▶ 타임프레임 비교 실행 중... (leverage=1x)")

timeframe_configs = [
    {
        'label':       '4h',
        'data_path':   'backtestDatas/btcusdt_4h.csv',
        'compression': 240,
        'est_window':  50,    # 50봉 × 4h = 200h ≈ 8.3일
        'max_bars':    48,    # 48봉      = 192h ≈ 8.0일
    },
    {
        'label':       '1h',
        'data_path':   'backtestDatas/btcusdt_1h.csv',
        'compression': 60,
        'est_window':  200,   # 200봉 × 1h = 200h ≈ 8.3일 (4h와 동일 룩백)
        'max_bars':    192,   # 192봉      = 192h ≈ 8.0일
    },
]

tf_results = []
for cfg in timeframe_configs:
    print(f"  {cfg['label']} ...", end=" ", flush=True)
    r = run_one(
        data_path   = cfg['data_path'],
        compression = cfg['compression'],
        est_window  = cfg['est_window'],
        max_bars    = cfg['max_bars'],
        leverage    = 1,
        params      = BASE_PARAMS,
    )
    tf_results.append(r)
    if r:
        print(f"ROR={r['ror']:+.1f}%  MDD={r['mdd']:.1f}%  Sharpe={r['sharpe']:.2f}")
    else:
        print("거래 없음")

print_table(
    title       = "타임프레임별 성과 (leverage=1x, 초기자본 $100,000)",
    rows        = tf_results,
    col_headers = ["ROR", "Sharpe", "MDD", "승률", "P/L비", "거래수"],
    row_labels  = [cfg['label'] for cfg in timeframe_configs],
)

# ══════════════════════════════════════════════════════════════════════
#  3. 타임프레임 × 레버리지 교차 매트릭스
# ══════════════════════════════════════════════════════════════════════
print("\n\n▶ 타임프레임 × 레버리지 교차 매트릭스 실행 중...")

matrix_leverages = [1, 2, 3, 5]   # 10x는 1h에서 MDD 극단적이라 별도 주석
matrix_results = {cfg['label']: [] for cfg in timeframe_configs}

for cfg in timeframe_configs:
    for lev in matrix_leverages:
        print(f"  {cfg['label']} × {lev}x ...", end=" ", flush=True)
        r = run_one(
            data_path   = cfg['data_path'],
            compression = cfg['compression'],
            est_window  = cfg['est_window'],
            max_bars    = cfg['max_bars'],
            leverage    = lev,
            params      = BASE_PARAMS,
        )
        matrix_results[cfg['label']].append(r)
        if r:
            print(f"ROR={r['ror']:+.1f}%  MDD={r['mdd']:.1f}%")
        else:
            print("거래 없음")

print(f"\n{'='*70}")
print(f"  타임프레임 × 레버리지 교차 매트릭스 (ROR / MDD / Sharpe)")
print(f"{'='*70}")
header = f"  {'':8s}" + "".join(f"{'lev '+str(l)+'x':>20s}" for l in matrix_leverages)
print(header)
print(f"  {'-'*68}")
for cfg in timeframe_configs:
    rors  = []
    for r in matrix_results[cfg['label']]:
        if r:
            rors.append(f"{r['ror']:+.1f}% / {r['mdd']:.1f}% / {r['sharpe']:.2f}")
        else:
            rors.append("N/A")
    row = f"  {cfg['label']:<8s}" + "".join(f"{v:>20s}" for v in rors)
    print(row)
print(f"{'='*70}")
print("  (각 셀: ROR / MDD / Sharpe)")
