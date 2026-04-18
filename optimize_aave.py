"""
AAVE 파라미터 최적화 — 2단계 Grid Search

Stage 1: 진입 파라미터 (bb_period, bb_std, rsi, adx)
Stage 2: 청산 파라미터 (target, trailing, vb_k, vb_min_range_pct)

스코어 = Sharpe × sqrt(거래수/100)
  — 최소 거래 수 30건 미만 제외
"""

import os, sys, itertools
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

from backtest_live_strategy import simulate, load_ohlcv

DATA_PATH  = 'backtestDatas/aaveusdt_4h.csv'
SYMBOL     = 'AAVEUSDT'
MIN_TRADES = 30

BASE_CFG = dict(
    path=DATA_PATH, symbol=SYMBOL,
    slippage_pct=0.0005,
    bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=30,
    adx_threshold=15, default_target=10.0,
    trailing=0.4, tight_trailing=0.65,
    vb_k=0.3, vb_min_range_pct=0.3,
)

STAGE1_GRID = {
    'bb_period':    [15, 20, 25],
    'bb_std':       [1.5, 2.0, 2.5],
    'rsi_overbuy':  [70, 80],
    'rsi_oversell': [20, 30],
    'adx_threshold':[10, 15, 20, 25],
}

STAGE2_GRID = {
    'default_target':    [7.0, 10.0, 15.0, 20.0],
    'trailing':          [0.3, 0.4, 0.5, 0.6],
    'tight_trailing':    [0.65, 0.75, 0.85],
    'vb_k':              [0.2, 0.3, 0.4, 0.5],
    'vb_min_range_pct':  [0.2, 0.3, 0.5],
}

INT_PARAMS = {'bb_period', 'rsi_overbuy', 'rsi_oversell', 'adx_threshold'}


def score(r) -> float:
    if r is None or r['total'] < MIN_TRADES:
        return -999.0
    return r['sharpe'] * np.sqrt(r['total'] / 100)


def run_grid(df, base_cfg, grid: dict, label: str):
    keys   = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    total  = len(combos)
    print(f"\n  [{label}]  조합 수: {total:,}")

    results = []
    for idx, combo in enumerate(combos):
        cfg = {**base_cfg, **dict(zip(keys, combo))}
        r, _, _ = simulate(df, cfg, use_xgb=True, sideways_mode='vb')
        sc = score(r)

        if idx % 50 == 0:
            print(f"    진행: {idx}/{total} ({idx/total*100:.0f}%)", end='\r')

        if r is not None and r['total'] >= MIN_TRADES:
            results.append({**dict(zip(keys, combo)),
                            'score': sc,
                            'ror':   r['ror'],
                            'sharpe':r['sharpe'],
                            'mdd':   r['mdd'],
                            'wr':    r['win_rate'],
                            'n':     r['total'],
                            'tr_n':  r['tr_count'],
                            'vb_n':  r['vb_count'],
                            })

    print(f"    완료: {total}/{total} (100%)")
    return pd.DataFrame(results).sort_values('score', ascending=False)


def print_top(df_res: pd.DataFrame, keys: list, n: int = 15):
    print(f"\n  TOP {n}:")
    print(f"  {'#':>3}  " + "  ".join(f"{k:>14}" for k in keys) +
          f"  {'ROR':>7}  {'Sharpe':>6}  {'MDD':>6}  {'WR':>5}  {'N':>4}  {'Score':>6}")
    print(f"  " + "-" * (3 + 16*len(keys) + 45))
    for rank, (_, row) in enumerate(df_res.head(n).iterrows(), 1):
        vals = "  ".join(f"{row[k]:>14.4g}" for k in keys)
        print(f"  #{rank:>2}  {vals}  "
              f"{row['ror']:>+6.1f}%  {row['sharpe']:>6.2f}  "
              f"{row['mdd']:>5.1f}%  {row['wr']:>4.1f}%  {int(row['n']):>4}  {row['score']:>6.3f}")

    best = df_res.iloc[0]
    print(f"\n  최적값:")
    for k in keys:
        print(f"    {k:20s} = {best[k]}")
    print(f"    → ROR {best['ror']:+.1f}%  Sharpe {best['sharpe']:.2f}  "
          f"MDD {best['mdd']:.1f}%  WR {best['wr']:.1f}%  N={int(best['n'])}")
    return best


if __name__ == '__main__':
    print("=" * 60)
    print("  AAVE 파라미터 최적화 (XGB+VB)")
    print("=" * 60)
    df = load_ohlcv(DATA_PATH)
    print(f"  {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉)")
    print(f"  최소 거래 수: {MIN_TRADES}건")

    # ── Stage 1 ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Stage 1 — 진입 파라미터 최적화")
    print(f"{'='*60}")
    s1_keys = list(STAGE1_GRID.keys())
    s1_res  = run_grid(df, BASE_CFG, STAGE1_GRID, "Stage1 진입")
    best1   = print_top(s1_res, s1_keys)

    s1_best = {k: (int(best1[k]) if k in INT_PARAMS else float(best1[k])) for k in s1_keys}
    stage2_base = {**BASE_CFG, **s1_best}

    # ── Stage 2 ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Stage 2 — 청산 파라미터 최적화")
    print(f"  (Stage1 최적 진입 파라미터 고정)")
    print(f"{'='*60}")
    s2_keys = list(STAGE2_GRID.keys())
    s2_res  = run_grid(df, stage2_base, STAGE2_GRID, "Stage2 청산")
    best2   = print_top(s2_res, s2_keys)

    s2_best = {k: (int(best2[k]) if k in INT_PARAMS else float(best2[k])) for k in s2_keys}
    final_cfg = {**stage2_base, **s2_best}

    # ── 최종 출력 ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  최종 최적 파라미터 (coins/aave/strategy.py 반영용)")
    print(f"{'='*60}")
    param_map = {
        'bb_period':        'TR_BB_PERIOD',
        'bb_std':           'TR_BB_STD',
        'rsi_overbuy':      'RSI_OVERBUY',
        'rsi_oversell':     'RSI_OVERSELL',
        'adx_threshold':    'ADX_THRESHOLD',
        'default_target':   'DEFAULT_TARGET_ROR',
        'trailing':         'TRAILING_RATIO',
        'tight_trailing':   'TIGHT_TRAILING_RATIO',
        'vb_k':             'VB_K',
        'vb_min_range_pct': 'VB_MIN_RANGE_PCT',
    }
    for cfg_key, class_attr in param_map.items():
        if cfg_key in final_cfg:
            print(f"  {class_attr:25s} = {final_cfg[cfg_key]}")

    print(f"\n  최종 파라미터로 검증 실행 중...")
    r_final, _, _ = simulate(df, final_cfg, use_xgb=True, sideways_mode='vb')
    if r_final:
        print(f"  ROR {r_final['ror']:+.1f}%  |  Sharpe {r_final['sharpe']:.2f}  "
              f"|  MDD {r_final['mdd']:.1f}%  |  WR {r_final['win_rate']:.1f}%  "
              f"|  N={r_final['total']} (TR:{r_final['tr_count']}/VB:{r_final['vb_count']})")
    print(f"{'='*60}")
