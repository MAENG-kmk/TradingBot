"""
ARB SDE 백테스트 — BTC SDE 전략 동일 적용

전략:
  진입: GBM μ,σ 추정 → P(목표 도달 > 손절 도달) > SDE_ENTRY_PROB
  청산:
    1. 하드스탑  : ROR ≤ -SDE_STOP_ROR%
    2. 목표 도달 : ROR ≥ +SDE_TARGET_ROR%
    3. 확률 역전 : P(지속) < SDE_EXIT_PROB
    4. 시간 초과 : SDE_MAX_BARS봉 (4H 기준 = 8일)

사용법:
  python backtest_sde_arb.py            # 기본
  python backtest_sde_arb.py --plot     # 자본 곡선 시각화
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

from tools.sdeTools import barrier_prob, estimate_gbm, sde_entry_probs

# ── 파라미터 ─────────────────────────────────────────────────────────
DATA_PATH      = 'backtestDatas/arbusdt_4h.csv'
COMMISSION     = 0.0005   # 편도 수수료율
SLIPPAGE       = 0.0003   # 편도 슬리피지
INITIAL        = 100_000.0
POSITION_PCT   = 0.10     # 자본 대비 포지션 비율
LEVERAGE       = 1        # ARB 레버리지

SDE_EST_WINDOW = 50       # GBM 추정 윈도우
SDE_TARGET_ROR = 0.04     # 목표 수익률 (4%)
SDE_STOP_ROR   = 0.02     # 손절 비율   (2%)
SDE_ENTRY_PROB = 0.58     # 진입 최소 확률
SDE_EXIT_PROB  = 0.35     # 확률 역전 청산 임계값
SDE_MAX_BARS   = 48       # 최대 보유 봉 수


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['Date'])
    df = df.rename(columns={'Date': 'time'})
    df = df.sort_values('time').reset_index(drop=True)
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['Close'])
    return df


def run_backtest(df: pd.DataFrame):
    closes = df['Close'].values.astype(float)
    n      = len(closes)

    capital  = INITIAL
    position = None   # dict or None
    trades   = []

    for i in range(SDE_EST_WINDOW + 1, n):
        S = closes[i]

        # ── 포지션 없음 → 진입 검토 ──────────────────────────────
        if position is None:
            price_arr = closes[:i]
            mu, sigma = estimate_gbm(price_arr, window=SDE_EST_WINDOW)
            if mu is None:
                continue

            p_long, p_short = sde_entry_probs(S, SDE_TARGET_ROR, SDE_STOP_ROR, mu, sigma)

            side = None
            if p_long > SDE_ENTRY_PROB and p_long >= p_short:
                side = 'long'
                p_entry = p_long
            elif p_short > SDE_ENTRY_PROB and p_short > p_long:
                side = 'short'
                p_entry = p_short

            if side is not None:
                entry_cost = S * (1 + SLIPPAGE) if side == 'long' else S * (1 - SLIPPAGE)
                notional   = capital * POSITION_PCT * LEVERAGE
                size       = notional / entry_cost

                if side == 'long':
                    sde_target_price = entry_cost * (1.0 + SDE_TARGET_ROR)
                    sde_stop_price   = entry_cost * (1.0 - SDE_STOP_ROR)
                else:
                    sde_target_price = entry_cost * (1.0 - SDE_TARGET_ROR)
                    sde_stop_price   = entry_cost * (1.0 + SDE_STOP_ROR)

                fee = notional * COMMISSION
                capital -= fee

                position = {
                    'side':         side,
                    'entry_bar':    i,
                    'entry_price':  entry_cost,
                    'size':         size,
                    'sde_target':   sde_target_price,
                    'sde_stop':     sde_stop_price,
                    'p_entry':      p_entry,
                }
            continue

        # ── 포지션 있음 → 청산 검토 ──────────────────────────────
        entry_price = position['entry_price']
        side        = position['side']
        entry_bar   = position['entry_bar']
        size        = position['size']
        sde_target  = position['sde_target']
        sde_stop    = position['sde_stop']

        # 현재 ROR 계산
        if side == 'long':
            ror = (S - entry_price) / entry_price
        else:
            ror = (entry_price - S) / entry_price

        # GBM 재추정 → 지속 확률
        price_arr = closes[:i]
        mu, sigma = estimate_gbm(price_arr, window=SDE_EST_WINDOW)
        if mu is not None:
            if side == 'long':
                p_cont = barrier_prob(S, sde_target, sde_stop, mu, sigma)
                at_target = S >= sde_target
                at_stop   = S <= sde_stop
            else:
                p_cont    = 1.0 - barrier_prob(S, sde_stop, sde_target, mu, sigma)
                at_target = S <= sde_target
                at_stop   = S >= sde_stop
        else:
            p_cont    = SDE_EXIT_PROB + 0.01   # 추정 불가면 유지
            at_target = False
            at_stop   = False

        bars_held  = i - entry_bar
        timed_out  = bars_held >= SDE_MAX_BARS

        should_close = False
        reason       = ''

        if at_stop:
            should_close = True
            reason = 'stop'
        elif at_target:
            should_close = True
            reason = 'target'
        elif p_cont < SDE_EXIT_PROB:
            should_close = True
            reason = 'prob_exit'
        elif timed_out:
            should_close = True
            reason = 'timeout'

        if should_close:
            exit_price = S * (1 - SLIPPAGE) if side == 'long' else S * (1 + SLIPPAGE)
            notional   = position['size'] * exit_price
            fee        = notional * COMMISSION
            if side == 'long':
                pnl = (exit_price - entry_price) * size - fee
            else:
                pnl = (entry_price - exit_price) * size - fee

            capital += pnl
            trades.append({
                'entry_bar':   entry_bar,
                'exit_bar':    i,
                'entry_price': entry_price,
                'exit_price':  exit_price,
                'side':        side,
                'ror_pct':     ror * 100,
                'pnl':         pnl,
                'capital':     capital,
                'bars_held':   bars_held,
                'reason':      reason,
                'p_entry':     position['p_entry'],
            })
            position = None

    return pd.DataFrame(trades), capital


def print_results(trades: pd.DataFrame, final_capital: float):
    if trades.empty:
        print("거래 없음")
        return

    total_trades = len(trades)
    wins         = (trades['pnl'] > 0).sum()
    losses       = (trades['pnl'] <= 0).sum()
    win_rate     = wins / total_trades * 100
    total_pnl    = trades['pnl'].sum()
    total_ror    = (final_capital - INITIAL) / INITIAL * 100
    avg_pnl      = trades['pnl'].mean()
    avg_ror      = trades['ror_pct'].mean()
    max_dd       = _max_drawdown(trades['capital'].values, INITIAL)
    avg_bars     = trades['bars_held'].mean()

    reason_counts = trades['reason'].value_counts().to_dict()

    print("=" * 55)
    print(f"  ARB SDE 백테스트 결과")
    print("=" * 55)
    print(f"  총 거래 수   : {total_trades}")
    print(f"  승률         : {win_rate:.1f}%  ({wins}승 {losses}패)")
    print(f"  총 손익      : {total_pnl:+,.2f} USD")
    print(f"  총 수익률    : {total_ror:+.2f}%")
    print(f"  평균 손익    : {avg_pnl:+.2f} USD")
    print(f"  평균 ROR     : {avg_ror:+.2f}%")
    print(f"  최대 낙폭    : {max_dd:.2f}%")
    print(f"  평균 보유 봉 : {avg_bars:.1f}봉 ({avg_bars*4:.0f}h)")
    print(f"  청산 사유 분포: {reason_counts}")
    print(f"  최종 자본    : {final_capital:,.2f} USD  (초기: {INITIAL:,.0f})")
    print("=" * 55)

    # 방향별
    for side in ['long', 'short']:
        sub = trades[trades['side'] == side]
        if sub.empty:
            continue
        sw = (sub['pnl'] > 0).sum()
        print(f"  [{side.upper():5}] {len(sub)}건 | 승률 {sw/len(sub)*100:.1f}% | "
              f"손익 {sub['pnl'].sum():+,.2f} | 평균 ROR {sub['ror_pct'].mean():+.2f}%")


def _max_drawdown(capitals, initial):
    equity = np.concatenate([[initial], capitals])
    peak   = np.maximum.accumulate(equity)
    dd     = (equity - peak) / peak * 100
    return float(dd.min())


def plot_equity(trades: pd.DataFrame, df_raw: pd.DataFrame):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    times = df_raw['time'].values

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)

    # 자본 곡선
    eq_x = [df_raw['time'].iloc[0]]
    eq_y = [INITIAL]
    for _, row in trades.iterrows():
        eq_x.append(df_raw['time'].iloc[int(row['exit_bar'])])
        eq_y.append(row['capital'])

    ax1.plot(eq_x, eq_y, color='cyan', linewidth=1.5)
    ax1.axhline(INITIAL, color='gray', linestyle='--', linewidth=0.8)
    ax1.set_title('ARB SDE Strategy — Equity Curve')
    ax1.set_ylabel('Capital (USD)')
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.grid(True, alpha=0.3)

    # 개별 거래 PnL
    colors = ['green' if p > 0 else 'red' for p in trades['pnl']]
    ax2.bar(range(len(trades)), trades['pnl'], color=colors, alpha=0.7)
    ax2.axhline(0, color='white', linewidth=0.8)
    ax2.set_title('Trade PnL')
    ax2.set_ylabel('PnL (USD)')
    ax2.set_xlabel('Trade #')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plot', action='store_true', help='자본 곡선 플롯')
    args = parser.parse_args()

    print(f"데이터 로드: {DATA_PATH}")
    df = load_data(DATA_PATH)
    print(f"  {len(df)}봉  {df['time'].iloc[0].date()} ~ {df['time'].iloc[-1].date()}")
    print(f"SDE 파라미터: TARGET={SDE_TARGET_ROR*100:.0f}% | STOP={SDE_STOP_ROR*100:.0f}% | "
          f"ENTRY_P={SDE_ENTRY_PROB} | EXIT_P={SDE_EXIT_PROB} | MAX_BARS={SDE_MAX_BARS}")
    print()

    trades, final_capital = run_backtest(df)
    print_results(trades, final_capital)

    if args.plot and not trades.empty:
        plot_equity(trades, df)
