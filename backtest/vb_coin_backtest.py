"""
DOGE VB 전략 → 전 코인 백테스트

전략: 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)
  진입: cur_open ± VB_K × prev_range 돌파 (고가/저가 터치)
  청산: 동일 캔들 종가 (bar close 청산) — 손절/트레일링 없음
  방향: 양방향 동시 트리거 시 스킵 (MA 필터 OFF)

DOGE 파라미터 (coins/doge/strategy.py 동일):
  VB_K=0.3, VB_MIN_RANGE_PCT=0.3%, LEVERAGE=1, POSITION_FRAC=10%

사용법:
  python -m backtest.vb_coin_backtest
  python -m backtest.vb_coin_backtest --coin btc
  python -m backtest.vb_coin_backtest --coin all
"""
import argparse
import os
import sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

# ─────────────────────────────────────────
# 파라미터 (DOGE strategy.py 동일)
# ─────────────────────────────────────────
VB_K             = 0.3
VB_MIN_RANGE_PCT = 0.3   # prev_range / prev_close 최소 %

INITIAL_CASH   = 10_000.0
POSITION_FRAC  = 0.1
LEVERAGE       = 1
COMMISSION_PCT = 0.0004  # Binance 선물 수수료
SLIPPAGE_PCT   = 0.0002  # 슬리피지

COINS = ["aave", "arb", "avax", "bnb", "btc",
         "doge", "eth", "link", "sol", "sui", "xrp"]


def load_4h(coin: str) -> pd.DataFrame | None:
    path = f"backtestDatas/{coin}usdt_4h.csv"
    if not os.path.exists(path):
        print(f"  [건너뜀] {path} 없음")
        return None
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def run_backtest(coin: str, quiet: bool = False) -> dict | None:
    df = load_4h(coin)
    if df is None or len(df) < 10:
        return None

    cash    = INITIAL_CASH
    fee_one = COMMISSION_PCT + SLIPPAGE_PCT  # 편도 수수료

    trades = []
    equity = []

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        cur  = df.iloc[i]

        prev_range = float(prev["High"] - prev["Low"])
        prev_close = float(prev["Close"])

        # 최소 변동폭 필터
        if (prev_close <= 0 or prev_range <= 0
                or prev_range / prev_close * 100 < VB_MIN_RANGE_PCT):
            equity.append(cash)
            continue

        cur_open  = float(cur["Open"])
        cur_high  = float(cur["High"])
        cur_low   = float(cur["Low"])
        cur_close = float(cur["Close"])

        long_trig  = cur_open + VB_K * prev_range
        short_trig = cur_open - VB_K * prev_range

        long_ok  = cur_high >= long_trig  and long_trig  > cur_open
        short_ok = cur_low  <= short_trig and short_trig < cur_open

        # 양방향 동시 트리거 → 방향 불명, 스킵
        if long_ok and short_ok:
            equity.append(cash)
            continue

        if long_ok:
            entry   = long_trig
            exit_   = cur_close
            raw_ror = (exit_ - entry) / entry * 100
            side    = "long"
        elif short_ok:
            entry   = short_trig
            exit_   = cur_close
            raw_ror = (entry - exit_) / entry * 100
            side    = "short"
        else:
            equity.append(cash)
            continue

        ror    = raw_ror - fee_one * 2 * 100  # 왕복 수수료 차감
        profit = cash * POSITION_FRAC * LEVERAGE * ror / 100
        cash  += profit

        trades.append({
            "ts":     df.index[i],
            "side":   side,
            "entry":  entry,
            "exit":   exit_,
            "ror":    ror,
            "profit": profit,
        })
        equity.append(cash)

    if not trades:
        if not quiet:
            print(f"\n  [{coin.upper()}] 거래 없음")
        return None

    df_t = pd.DataFrame(trades)
    eq   = np.array(equity, dtype=float)

    total    = len(df_t)
    won      = (df_t["ror"] > 0).sum()
    lost     = (df_t["ror"] <= 0).sum()
    win_rate = won / total * 100
    final    = eq[-1]
    ror_total = (final - INITIAL_CASH) / INITIAL_CASH * 100

    avg_win  = df_t.loc[df_t["ror"] > 0,  "ror"].mean() if won  > 0 else 0.0
    avg_loss = df_t.loc[df_t["ror"] <= 0, "ror"].mean() if lost > 0 else 0.0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

    long_cnt  = (df_t["side"] == "long").sum()
    short_cnt = (df_t["side"] == "short").sum()

    returns = pd.Series(eq).pct_change().dropna()
    sharpe  = (returns.mean() / returns.std() * np.sqrt(2190)
               if returns.std() > 0 else 0.0)

    running_max = np.maximum.accumulate(eq)
    dd  = (eq - running_max) / running_max * 100
    mdd = float(dd.min()) if len(dd) > 0 else 0.0

    if not quiet:
        print(f"\n{'='*55}")
        print(f"  {coin.upper():>6}USDT  4H VB 전략")
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉)")
        print(f"{'='*55}")
        print(f"  총 거래:  {total}회  (롱 {long_cnt} / 숏 {short_cnt})")
        print(f"  승률:     {win_rate:.1f}%  (수익 {won} / 손실 {lost})")
        print(f"  P/L 비:   {pl_ratio:.2f}  (avg win {avg_win:+.2f}% / loss {avg_loss:+.2f}%)")
        print(f"\n  ROR:      {ror_total:+.2f}%")
        print(f"  Sharpe:   {sharpe:.2f}")
        print(f"  MDD:      {mdd:.2f}%")
        print(f"  최종자본: ${final:,.2f}  (초기 ${INITIAL_CASH:,.0f})")

        # 연도별 수익
        eq_index  = df.index[1:1 + len(eq)]
        eq_series = pd.Series(eq, index=eq_index)
        prev_val  = INITIAL_CASH
        print(f"\n  연도별 수익:")
        for year, grp in eq_series.groupby(eq_series.index.year):
            end_val = grp.iloc[-1]
            yr      = (end_val - prev_val) / prev_val * 100
            sign    = "+" if yr >= 0 else ""
            bar     = "█" * min(int(abs(yr) / 10), 40)
            print(f"    {year}: {sign}{yr:6.1f}%  {bar}")
            prev_val = end_val

    return {
        "coin":     coin.upper(),
        "ror":      ror_total,
        "sharpe":   sharpe,
        "mdd":      mdd,
        "trades":   total,
        "win_rate": win_rate,
        "pl_ratio": pl_ratio,
        "long_cnt": long_cnt,
        "short_cnt": short_cnt,
        "final":    final,
    }


def _print_summary(results: list[dict]):
    if len(results) <= 1:
        return
    print(f"\n{'='*72}")
    print(f"  VB 전략 전체 요약  (k={VB_K}, min_range={VB_MIN_RANGE_PCT}%, 종가청산, LEVERAGE={LEVERAGE})")
    print(f"{'='*72}")
    print(f"  {'코인':<8} {'ROR':>10}  {'Sharpe':>7}  {'MDD':>7}  {'거래':>5}  {'승률':>6}  {'P/L':>5}")
    print(f"  {'─'*68}")
    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True):
        print(f"  {r['coin']:<8} {r['ror']:>+9.1f}%  {r['sharpe']:>7.2f}  "
              f"{r['mdd']:>6.1f}%  {r['trades']:>5}  {r['win_rate']:>5.1f}%  {r['pl_ratio']:>5.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VB 전략 코인 백테스트")
    parser.add_argument("--coin", default="all",
                        choices=COINS + ["all"],
                        help="코인 코드 또는 all (기본: all)")
    args = parser.parse_args()

    targets = COINS if args.coin == "all" else [args.coin]
    results = []
    for c in targets:
        r = run_backtest(c)
        if r:
            results.append(r)
    _print_summary(results)
