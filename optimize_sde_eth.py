"""
ETH SDE 파라미터 최적화 — Grid Search

탐색 파라미터:
  SDE_EST_WINDOW  : GBM 추정 윈도우 봉 수
  SDE_TARGET_ROR  : 목표 수익률
  SDE_STOP_ROR    : 손절 비율
  SDE_ENTRY_PROB  : 진입 최소 확률
  SDE_EXIT_PROB   : 확률 역전 청산 임계값
  SDE_MAX_BARS    : 최대 보유 봉 수

스코어 = 총수익률 × (승률/100) / abs(최대낙폭)
  — 수익, 승률, 드로다운을 동시에 고려
  — 거래 수 < 15이면 제외 (통계 유의성)
"""

import os, sys, itertools
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

from tools.sdeTools import barrier_prob, estimate_gbm, sde_entry_probs

# ── 고정 파라미터 ─────────────────────────────────────────────────────
DATA_PATH    = 'backtestDatas/ethusdt_4h.csv'
COMMISSION   = 0.0005
SLIPPAGE     = 0.0002   # ETH는 유동성이 높아 슬리피지 낮음
INITIAL      = 100_000.0
POSITION_PCT = 0.10
LEVERAGE     = 1
MIN_TRADES   = 15       # ETH 데이터가 길어 기준 높임

# ── 탐색 그리드 ──────────────────────────────────────────────────────
GRID = {
    'est_window':  [20, 30, 50, 70, 100],
    'target_ror':  [0.03, 0.05, 0.07, 0.10, 0.15],
    'stop_ror':    [0.015, 0.02, 0.03, 0.05],
    'entry_prob':  [0.52, 0.55, 0.58, 0.62, 0.65],
    'exit_prob':   [0.25, 0.30, 0.35, 0.42],
    'max_bars':    [24, 48, 96],
}


def load_data(path: str) -> np.ndarray:
    df = pd.read_csv(path, parse_dates=['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    df = df.dropna(subset=['Close'])
    return df['Close'].values.astype(float), df['Date'].values


def run_backtest(closes, est_window, target_ror, stop_ror,
                 entry_prob, exit_prob, max_bars):
    n        = len(closes)
    capital  = INITIAL
    position = None
    wins = losses = 0
    equity = [INITIAL]

    for i in range(est_window + 1, n):
        S = closes[i]

        if position is None:
            mu, sigma = estimate_gbm(closes[:i], window=est_window)
            if mu is None:
                continue

            p_long, p_short = sde_entry_probs(S, target_ror, stop_ror, mu, sigma)

            side = None
            if p_long > entry_prob and p_long >= p_short:
                side = 'long'
            elif p_short > entry_prob and p_short > p_long:
                side = 'short'

            if side is not None:
                entry_cost = S * (1 + SLIPPAGE) if side == 'long' else S * (1 - SLIPPAGE)
                notional   = capital * POSITION_PCT * LEVERAGE
                size       = notional / entry_cost
                tgt_p = entry_cost * (1 + target_ror) if side == 'long' else entry_cost * (1 - target_ror)
                stp_p = entry_cost * (1 - stop_ror)   if side == 'long' else entry_cost * (1 + stop_ror)
                capital -= notional * COMMISSION
                position = dict(side=side, entry_bar=i, entry_price=entry_cost,
                                size=size, tgt=tgt_p, stp=stp_p)
            continue

        side  = position['side']
        ep    = position['entry_price']
        size  = position['size']
        tgt   = position['tgt']
        stp   = position['stp']
        bars  = i - position['entry_bar']

        mu, sigma = estimate_gbm(closes[:i], window=est_window)
        if mu is not None:
            if side == 'long':
                p_cont    = barrier_prob(S, tgt, stp, mu, sigma)
                at_target = S >= tgt
                at_stop   = S <= stp
            else:
                p_cont    = 1.0 - barrier_prob(S, stp, tgt, mu, sigma)
                at_target = S <= tgt
                at_stop   = S >= stp
        else:
            p_cont = exit_prob + 0.01
            at_target = at_stop = False

        should_close = at_stop or at_target or (p_cont < exit_prob) or (bars >= max_bars)

        if should_close:
            xp  = S * (1 - SLIPPAGE) if side == 'long' else S * (1 + SLIPPAGE)
            fee = size * xp * COMMISSION
            pnl = ((xp - ep) * size - fee) if side == 'long' else ((ep - xp) * size - fee)
            capital += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1
            equity.append(capital)
            position = None

    n_trades = wins + losses
    if n_trades < MIN_TRADES:
        return None

    total_ror = (capital - INITIAL) / INITIAL * 100
    win_rate  = wins / n_trades * 100

    eq   = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd   = (eq - peak) / peak * 100
    max_dd = float(dd.min())

    if max_dd >= 0:
        return None

    score = total_ror * (win_rate / 100) / abs(max_dd)

    return {
        'score':     score,
        'total_ror': total_ror,
        'win_rate':  win_rate,
        'max_dd':    max_dd,
        'n_trades':  n_trades,
    }


def main():
    print(f"데이터 로드: {DATA_PATH}")
    closes, dates = load_data(DATA_PATH)
    print(f"  {len(closes)}봉  {str(dates[0])[:10]} ~ {str(dates[-1])[:10]}")

    keys   = list(GRID.keys())
    values = list(GRID.values())
    combos = list(itertools.product(*values))
    total  = len(combos)
    print(f"총 조합 수: {total:,}  (MIN_TRADES={MIN_TRADES})")
    print("최적화 중...\n")

    results = []
    for idx, combo in enumerate(combos):
        params = dict(zip(keys, combo))

        if params['stop_ror'] >= params['target_ror']:
            continue

        res = run_backtest(
            closes,
            est_window = params['est_window'],
            target_ror = params['target_ror'],
            stop_ror   = params['stop_ror'],
            entry_prob = params['entry_prob'],
            exit_prob  = params['exit_prob'],
            max_bars   = params['max_bars'],
        )

        if idx % 500 == 0:
            print(f"  진행: {idx}/{total} ({idx/total*100:.0f}%)")

        if res is not None and res['score'] > 0:
            results.append({**params, **res})

    if not results:
        print("유효한 결과 없음")
        return

    df_res = pd.DataFrame(results).sort_values('score', ascending=False)

    print("\n" + "=" * 80)
    print("  TOP 20 파라미터 조합")
    print("=" * 80)
    for rank, (_, row) in enumerate(df_res.head(20).iterrows(), 1):
        print(
            f"  #{rank:2d}  "
            f"win={int(row['est_window']):3d}봉 | "
            f"tgt={row['target_ror']*100:.0f}% | "
            f"stp={row['stop_ror']*100:.1f}% | "
            f"ent={row['entry_prob']:.2f} | "
            f"ext={row['exit_prob']:.2f} | "
            f"bars={int(row['max_bars']):2d} | "
            f"ROR={row['total_ror']:+.1f}% | "
            f"승률={row['win_rate']:.1f}% | "
            f"DD={row['max_dd']:.1f}% | "
            f"N={int(row['n_trades'])} | "
            f"score={row['score']:.3f}"
        )

    best = df_res.iloc[0]
    print("\n" + "=" * 80)
    print("  최적 파라미터")
    print("=" * 80)
    print(f"  SDE_EST_WINDOW = {int(best['est_window'])}")
    print(f"  SDE_TARGET_ROR = {best['target_ror']:.3f}  ({best['target_ror']*100:.0f}%)")
    print(f"  SDE_STOP_ROR   = {best['stop_ror']:.3f}  ({best['stop_ror']*100:.1f}%)")
    print(f"  SDE_ENTRY_PROB = {best['entry_prob']:.2f}")
    print(f"  SDE_EXIT_PROB  = {best['exit_prob']:.2f}")
    print(f"  SDE_MAX_BARS   = {int(best['max_bars'])}")
    print(f"\n  → 총수익률 {best['total_ror']:+.2f}% | 승률 {best['win_rate']:.1f}% | "
          f"최대낙폭 {best['max_dd']:.1f}% | {int(best['n_trades'])}건")
    print("=" * 80)

    print("\n  [파라미터별 상위 30 평균값 — 수렴 경향 확인]")
    top30 = df_res.head(30)
    for k in keys:
        vals = top30[k].values
        print(f"    {k:15s}: avg={vals.mean():.4f}  min={vals.min():.4f}  max={vals.max():.4f}")

    # 수익률 기준 TOP5도 별도 출력 (스코어와 다를 수 있음)
    print("\n  [수익률 기준 TOP 5]")
    top_ror = df_res.sort_values('total_ror', ascending=False).head(5)
    for rank, (_, row) in enumerate(top_ror.iterrows(), 1):
        print(
            f"  #{rank}  ROR={row['total_ror']:+.1f}% | 승률={row['win_rate']:.1f}% | "
            f"DD={row['max_dd']:.1f}% | N={int(row['n_trades'])} | "
            f"tgt={row['target_ror']*100:.0f}% stp={row['stop_ror']*100:.1f}% "
            f"ent={row['entry_prob']:.2f} ext={row['exit_prob']:.2f} "
            f"win={int(row['est_window'])}봉 bars={int(row['max_bars'])}"
        )


if __name__ == '__main__':
    main()
