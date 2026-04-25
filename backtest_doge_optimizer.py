# backtest_doge_optimizer.py
"""
DOGE 150x MTF 추세추종 — TP% 최적화
실행: python backtest_doge_optimizer.py
      python backtest_doge_optimizer.py --save
"""
import argparse
import os
import sys
import time
sys.path.append(os.path.abspath('.'))

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt

from backtestStrategy.DogeMultiTFBacktest import load_and_compute_signals, run_backtest

DATA_PATH       = 'backtestDatas/dogeusdt_1m.csv'
INITIAL_CAPITAL = 10_000.0
TP_RANGE        = np.arange(0.3, 3.05, 0.1)   # 0.3% ~ 3.0%


def optimize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(TP_RANGE)
    for idx, tp in enumerate(TP_RANGE, 1):
        r = run_backtest(df, tp_pct=round(tp, 2), initial_capital=INITIAL_CAPITAL)
        rows.append(r)
        print(f"  [{idx:2d}/{total}] TP {tp:.1f}% → ROR {r['ror']:+7.1f}%  "
              f"Win {r['win_rate']:5.1f}%  Trades {r['total']:4d}  "
              f"MDD {r['mdd']:5.1f}%  Liq {r['n_liq']:4d}")
    return pd.DataFrame(rows)


def print_table(results: pd.DataFrame):
    print('\n' + '=' * 72)
    print(f"{'TP%':>5} {'총수익률':>9} {'승률':>7} {'거래':>6} "
          f"{'강청':>6} {'MDD':>7} {'최종자본':>12}")
    print('-' * 72)
    for _, r in results.sort_values('ror', ascending=False).iterrows():
        print(f"{r['tp_pct']:>4.1f}%  "
              f"{r['ror']:>+8.1f}%  "
              f"{r['win_rate']:>6.1f}%  "
              f"{r['total']:>5.0f}  "
              f"{r['n_liq']:>5.0f}  "
              f"{r['mdd']:>6.1f}%  "
              f"${r['final']:>10,.0f}")
    print('=' * 72)


def plot_results(results: pd.DataFrame, df: pd.DataFrame, save_path=None):
    if save_path:
        matplotlib.use('Agg')

    best_tp = results.loc[results['ror'].idxmax(), 'tp_pct']
    best_r  = run_backtest(df, tp_pct=best_tp, initial_capital=INITIAL_CAPITAL,
                           track_equity=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10), facecolor='#1e1e1e')
    fig.suptitle(f'DOGE 150x MTF 추세추종 — TP% 최적화 결과', color='white', fontsize=14)

    colors = ['#00b4d8', '#26a69a', '#ffa726', '#ef5350']

    # ── 패널 1: TP% vs 총수익률 ──────────────────────────────
    ax = axes[0, 0]
    ax.set_facecolor('#2b2b2b')
    bar_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in results['ror']]
    ax.bar(results['tp_pct'], results['ror'], color=bar_colors, width=0.08)
    ax.axhline(0, color='#555', linewidth=0.8)
    ax.set_xlabel('Take Profit (%)', color='#ccc')
    ax.set_ylabel('Total Return (%)', color='#ccc')
    ax.set_title('TP% vs 총수익률', color='white')
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values(): sp.set_color('#444')
    ax.axvline(best_tp, color='#ffa726', linestyle='--', linewidth=1.5,
               label=f'Best: {best_tp:.1f}%')
    ax.legend(facecolor='#333', labelcolor='white')

    # ── 패널 2: TP% vs 승률 ───────────────────────────────────
    ax = axes[0, 1]
    ax.set_facecolor('#2b2b2b')
    ax.plot(results['tp_pct'], results['win_rate'], color='#00b4d8',
            marker='o', markersize=4, linewidth=1.5)
    ax.set_xlabel('Take Profit (%)', color='#ccc')
    ax.set_ylabel('Win Rate (%)', color='#ccc')
    ax.set_title('TP% vs 승률', color='white')
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values(): sp.set_color('#444')

    # ── 패널 3: 최적 TP 에쿼티 커브 ──────────────────────────
    ax = axes[1, 0]
    ax.set_facecolor('#2b2b2b')
    eq_values = np.array(best_r['equity'])
    ax.plot(eq_values / INITIAL_CAPITAL * 100, color='#26a69a', linewidth=1.0)
    ax.axhline(100, color='#555', linestyle=':', linewidth=0.8)
    ax.set_xlabel('Bar', color='#ccc')
    ax.set_ylabel('Portfolio (%)', color='#ccc')
    ax.set_title(f'Best TP {best_tp:.1f}% — 에쿼티 커브  '
                 f'(ROR {best_r["ror"]:+.1f}%  MDD {best_r["mdd"]:.1f}%)',
                 color='white', fontsize=10)
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values(): sp.set_color('#444')

    # ── 패널 4: TP% vs MDD ────────────────────────────────────
    ax = axes[1, 1]
    ax.set_facecolor('#2b2b2b')
    ax.plot(results['tp_pct'], results['mdd'], color='#ef5350',
            marker='o', markersize=4, linewidth=1.5)
    ax.set_xlabel('Take Profit (%)', color='#ccc')
    ax.set_ylabel('MDD (%)', color='#ccc')
    ax.set_title('TP% vs 최대 낙폭(MDD)', color='white')
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values(): sp.set_color('#444')

    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='#1e1e1e')
        print(f"\n차트 저장: {save_path}")
    else:
        plt.show()
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DOGE 150x TP% 최적화')
    parser.add_argument('--save', action='store_true', help='차트 PNG 저장')
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"데이터 없음: {DATA_PATH}")
        sys.exit(1)

    print("데이터 로드 및 MTF 신호 계산 중...")
    t0 = time.time()
    df = load_and_compute_signals(DATA_PATH)
    print(f"완료 ({time.time()-t0:.1f}s) — {len(df):,}봉  "
          f"롱신호: {df['long_signal'].sum():,}  숏신호: {df['short_signal'].sum():,}\n")

    print("TP% 최적화 실행 중...")
    results = optimize(df)

    print_table(results)

    best_tp  = results.loc[results['ror'].idxmax(), 'tp_pct']
    best_ror = results['ror'].max()
    print(f"\n★ 최적 TP: {best_tp:.1f}%  →  총수익률 {best_ror:+.1f}%")

    if args.save:
        plot_results(results, df, save_path='charts/doge_tp_optimization.png')
    else:
        plot_results(results, df)
