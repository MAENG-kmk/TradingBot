"""
Multi-Timeframe EMA 9/21 + Regime Filter + VB 전략 백테스트 — BNB

레짐 필터 (ADX 14 + 회귀 기울기):
  추세장 → MTF EMA 9/21 전략
    진입: 1D/4H/1H 모두 EMA9>EMA21 + 1H 골든크로스 → LONG
          1D/4H/1H 모두 EMA9<EMA21 + 1H 데스크로스 → SHORT
    청산: 3개 TF 중 하나라도 정렬 이탈

  횡보장 → VB (변동성 돌파) 전략
    진입: open ± VB_K × prev_range 돌파
    청산: 다음 봉 무조건 청산

사용법:
  python -m backtest.mtf_ema_backtest
  python -m backtest.mtf_ema_backtest --optimize
  python -m backtest.mtf_ema_backtest --coin bnb --fast 9 --slow 21 --vb_k 0.3 --vb_min_range 0.3
"""
import argparse
import sys
import os
sys.path.append(os.path.abspath("."))

import pandas as pd
import numpy as np
from itertools import product as iterproduct

# ─────────────────────────────────────────
# 공통 설정
# ─────────────────────────────────────────
COMMISSION = 0.0005
SLIPPAGE   = 0.0003
INITIAL_CASH  = 100_000.0
POSITION_FRAC = 0.1

ADX_PERIOD      = 14
ADX_THRESHOLD   = 15
SLOPE_PERIOD    = 20
SLOPE_THRESHOLD = 0.05   # % (정규화된 기울기 임계값)


# ─────────────────────────────────────────
# 데이터 / 지표 함수
# ─────────────────────────────────────────
def load_1h(coin: str) -> pd.DataFrame:
    path = f"backtestDatas/{coin}usdt_1h.csv"
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    df.index = df.index.tz_localize(None)
    df.columns = [c.capitalize() for c in df.columns]
    return df


def add_ema(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    df[f"ema{fast}"] = df["Close"].ewm(span=fast, adjust=False).mean()
    df[f"ema{slow}"] = df["Close"].ewm(span=slow, adjust=False).mean()
    return df


def resample_ema(df_1h: pd.DataFrame, rule: str, fast: int, slow: int) -> pd.DataFrame:
    agg = df_1h.resample(rule).agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    agg[f"ema{fast}"] = agg["Close"].ewm(span=fast, adjust=False).mean()
    agg[f"ema{slow}"] = agg["Close"].ewm(span=slow, adjust=False).mean()
    # 룩어헤드 방지: 전봉 값만 사용
    agg[f"ema{fast}"] = agg[f"ema{fast}"].shift(1)
    agg[f"ema{slow}"] = agg[f"ema{slow}"].shift(1)
    return agg[[f"ema{fast}", f"ema{slow}"]].reindex(df_1h.index, method="ffill")


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ADX (14봉 기준)"""
    high  = df["High"].values.astype(float)
    low   = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n = len(close)

    tr      = np.zeros(n)
    dm_plus = np.zeros(n)
    dm_minus = np.zeros(n)

    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
        h_diff = high[i] - high[i - 1]
        l_diff = low[i - 1] - low[i]
        dm_plus[i]  = h_diff if h_diff > l_diff and h_diff > 0 else 0.0
        dm_minus[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0.0

    # Wilder 평활: TR / +DM / -DM
    tr_s = np.zeros(n)
    dp_s = np.zeros(n)
    dm_s = np.zeros(n)

    if period < n:
        tr_s[period]  = tr[1:period + 1].sum()
        dp_s[period]  = dm_plus[1:period + 1].sum()
        dm_s[period]  = dm_minus[1:period + 1].sum()
        for i in range(period + 1, n):
            tr_s[i]  = tr_s[i - 1]  - tr_s[i - 1]  / period + tr[i]
            dp_s[i]  = dp_s[i - 1]  - dp_s[i - 1]  / period + dm_plus[i]
            dm_s[i]  = dm_s[i - 1]  - dm_s[i - 1]  / period + dm_minus[i]

    di_plus  = np.where(tr_s > 0, 100.0 * dp_s / tr_s, 0.0)
    di_minus = np.where(tr_s > 0, 100.0 * dm_s / tr_s, 0.0)
    denom    = di_plus + di_minus
    dx       = np.where(denom > 0, 100.0 * np.abs(di_plus - di_minus) / denom, 0.0)

    # Wilder 평활: ADX
    adx = np.full(n, np.nan)
    start = 2 * period
    if start < n:
        adx[start] = dx[period + 1: start + 1].mean()
        for i in range(start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return pd.Series(adx, index=df.index)


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """정규화된 선형회귀 기울기 (백분율 / 봉)"""
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var  = np.sum((x - x_mean) ** 2)
    vals   = series.values.astype(float)
    result = np.full(len(vals), np.nan)

    for i in range(window - 1, len(vals)):
        y = vals[i - window + 1: i + 1]
        y_mean = y.mean()
        if y_mean == 0:
            continue
        slope = np.sum((x - x_mean) * (y - y_mean)) / x_var
        result[i] = (slope / y_mean) * 100.0

    return pd.Series(result, index=series.index)


def add_regime(df: pd.DataFrame,
               adx_period: int = ADX_PERIOD,
               adx_threshold: int = ADX_THRESHOLD,
               slope_period: int = SLOPE_PERIOD,
               slope_threshold: float = SLOPE_THRESHOLD) -> pd.DataFrame:
    """ADX + 회귀기울기 기반 레짐 컬럼 추가: 'trend' | 'ranging'"""
    adx = compute_adx(df, adx_period)
    adx_prev1 = adx.shift(1)
    adx_prev2 = adx.shift(2)

    is_trending = (
        (adx >= adx_threshold) |
        ((adx > 15) & (adx > adx_prev1) & (adx_prev1 > adx_prev2))
    )

    slope = _rolling_slope(df["Close"], slope_period)

    df["adx"]    = adx
    df["slope"]  = slope
    df["regime"] = np.where(
        is_trending & (slope.abs() > slope_threshold),
        "trend", "ranging"
    )
    return df


def add_vb_signals(df: pd.DataFrame,
                   vb_k: float = 0.3,
                   vb_min_range_pct: float = 0.3) -> pd.DataFrame:
    """VB 진입 신호 추가 (1H 기준)"""
    prev_high  = df["High"].shift(1)
    prev_low   = df["Low"].shift(1)
    prev_close = df["Close"].shift(1)
    prev_range = prev_high - prev_low

    range_ok = (prev_range / prev_close * 100) >= vb_min_range_pct

    cur_open       = df["Open"]
    long_trig      = cur_open + vb_k * prev_range
    short_trig     = cur_open - vb_k * prev_range

    df["vb_long_trig"]  = long_trig
    df["vb_short_trig"] = short_trig
    df["vb_long"]  = range_ok & (df["High"] >= long_trig)  & (df["Low"]  > short_trig)
    df["vb_short"] = range_ok & (df["Low"]  <= short_trig) & (df["High"] < long_trig)
    return df


# ─────────────────────────────────────────
# 백테스트 메인
# ─────────────────────────────────────────
def run_backtest(coin: str = "bnb", fast: int = 9, slow: int = 21,
                 vb_k: float = 0.3, vb_min_range_pct: float = 0.3,
                 verbose: bool = False, quiet: bool = False) -> dict | None:

    if not quiet:
        print(f"\n{'='*60}")
        print(f"  MTF EMA {fast}/{slow} + Regime + VB 백테스트 — {coin.upper()}")
        print(f"  VB_K={vb_k}  VB_MIN_RANGE={vb_min_range_pct}%")
        print(f"{'='*60}")

    # ── 데이터 로드 ──────────────────────────────────
    df = load_1h(coin)

    # 1H EMA (룩어헤드 방지: shift(1))
    df = add_ema(df, fast, slow)
    df[f"h1_ema{fast}"] = df[f"ema{fast}"].shift(1)
    df[f"h1_ema{slow}"] = df[f"ema{slow}"].shift(1)

    # 4H / 1D EMA
    h4 = resample_ema(df, "4h", fast, slow)
    df[f"h4_ema{fast}"] = h4[f"ema{fast}"]
    df[f"h4_ema{slow}"] = h4[f"ema{slow}"]

    d1 = resample_ema(df, "1D", fast, slow)
    df[f"d1_ema{fast}"] = d1[f"ema{fast}"]
    df[f"d1_ema{slow}"] = d1[f"ema{slow}"]

    # 레짐 필터
    df = add_regime(df)

    # VB 신호
    df = add_vb_signals(df, vb_k, vb_min_range_pct)

    df.dropna(inplace=True)

    # ── MTF EMA 정렬 판단 ─────────────────────────────
    df["bull_1h"] = df[f"h1_ema{fast}"] > df[f"h1_ema{slow}"]
    df["bull_4h"] = df[f"h4_ema{fast}"] > df[f"h4_ema{slow}"]
    df["bull_1d"] = df[f"d1_ema{fast}"] > df[f"d1_ema{slow}"]

    df["bear_1h"] = df[f"h1_ema{fast}"] < df[f"h1_ema{slow}"]
    df["bear_4h"] = df[f"h4_ema{fast}"] < df[f"h4_ema{slow}"]
    df["bear_1d"] = df[f"d1_ema{fast}"] < df[f"d1_ema{slow}"]

    df["prev_bull_1h"] = df["bull_1h"].shift(1).fillna(False).astype(bool)
    df["prev_bear_1h"] = df["bear_1h"].shift(1).fillna(False).astype(bool)

    df["golden_cross"] = (~df["prev_bull_1h"]) & df["bull_1h"]
    df["death_cross"]  = (~df["prev_bear_1h"]) & df["bear_1h"]

    df["signal_long"]  = df["golden_cross"] & df["bull_4h"] & df["bull_1d"]
    df["signal_short"] = df["death_cross"]  & df["bear_4h"] & df["bear_1d"]

    # ── 백테스트 루프 ─────────────────────────────────
    fee  = COMMISSION + SLIPPAGE
    cash = INITIAL_CASH
    pos  = 0.0
    entry = 0.0
    side  = None
    trade_mode   = None   # 'ema' | 'vb'
    entry_time   = None
    bars_in_trade = 0
    trades  = []
    equity  = []

    for ts, row in df.iterrows():
        price = float(row["Close"])

        # ── 포지션 보유 중 ────────────────────────────
        if side is not None:
            bars_in_trade += 1

            if trade_mode == 'vb':
                # VB: 진입 다음 봉 무조건 청산
                if bars_in_trade >= 1:
                    if side == 'long':
                        exit_price = price * (1 - fee)
                        pnl    = (exit_price - entry) / entry * 100
                        profit = abs(pos) * (exit_price - entry)
                    else:
                        exit_price = price * (1 + fee)
                        pnl    = (entry - exit_price) / entry * 100
                        profit = abs(pos) * (entry - exit_price)
                    cash += abs(pos) * entry + profit
                    trades.append({
                        "entry_time": entry_time, "exit_time": ts,
                        "side": side, "mode": "vb",
                        "entry": entry, "exit": exit_price,
                        "ror": pnl, "profit": profit,
                    })
                    pos, entry, side, trade_mode, bars_in_trade = 0.0, 0.0, None, None, 0

            else:  # 'ema'
                # MTF EMA: 정렬 이탈 시 청산
                close_signal = (
                    (side == 'long'  and (row["bear_1h"] or row["bear_4h"] or row["bear_1d"])) or
                    (side == 'short' and (row["bull_1h"] or row["bull_4h"] or row["bull_1d"]))
                )
                if close_signal:
                    if side == 'long':
                        exit_price = price * (1 - fee)
                        pnl    = (exit_price - entry) / entry * 100
                        profit = abs(pos) * (exit_price - entry)
                    else:
                        exit_price = price * (1 + fee)
                        pnl    = (entry - exit_price) / entry * 100
                        profit = abs(pos) * (entry - exit_price)
                    cash += abs(pos) * entry + profit
                    trades.append({
                        "entry_time": entry_time, "exit_time": ts,
                        "side": side, "mode": "ema",
                        "entry": entry, "exit": exit_price,
                        "ror": pnl, "profit": profit,
                    })
                    pos, entry, side, trade_mode, bars_in_trade = 0.0, 0.0, None, None, 0

        # ── 포지션 없음: 진입 ────────────────────────
        if side is None:
            value  = cash * POSITION_FRAC
            regime = row["regime"]

            if regime == 'trend':
                # MTF EMA 진입
                if row["signal_long"]:
                    entry_price = price * (1 + fee)
                    pos = value / entry_price
                    cash -= value
                    entry, side, trade_mode, entry_time, bars_in_trade = \
                        entry_price, 'long', 'ema', ts, 0
                elif row["signal_short"]:
                    entry_price = price * (1 - fee)
                    pos = -value / entry_price
                    cash -= value
                    entry, side, trade_mode, entry_time, bars_in_trade = \
                        entry_price, 'short', 'ema', ts, 0
            else:  # ranging
                # VB 진입
                if row["vb_long"] and not pd.isna(row["vb_long_trig"]):
                    entry_price = float(row["vb_long_trig"]) * (1 + fee)
                    if entry_price > 0:
                        pos = value / entry_price
                        cash -= value
                        entry, side, trade_mode, entry_time, bars_in_trade = \
                            entry_price, 'long', 'vb', ts, 0
                elif row["vb_short"] and not pd.isna(row["vb_short_trig"]):
                    entry_price = float(row["vb_short_trig"]) * (1 - fee)
                    if entry_price > 0:
                        pos = -value / entry_price
                        cash -= value
                        entry, side, trade_mode, entry_time, bars_in_trade = \
                            entry_price, 'short', 'vb', ts, 0

        # 자산 기록
        if side == 'long':
            equity.append(cash + abs(pos) * price)
        elif side == 'short':
            equity.append(cash + abs(pos) * entry - abs(pos) * (price - entry))
        else:
            equity.append(cash)

    # ── 미청산 포지션 강제 종료 ───────────────────
    if side and len(df) > 0:
        last_price = float(df["Close"].iloc[-1])
        if side == 'long':
            exit_price = last_price * (1 - fee)
            pnl    = (exit_price - entry) / entry * 100
            profit = abs(pos) * (exit_price - entry)
        else:
            exit_price = last_price * (1 + fee)
            pnl    = (entry - exit_price) / entry * 100
            profit = abs(pos) * (entry - exit_price)
        trades.append({
            "entry_time": entry_time, "exit_time": df.index[-1],
            "side": side, "mode": trade_mode,
            "entry": entry, "exit": exit_price,
            "ror": pnl, "profit": profit,
        })
        cash += abs(pos) * entry + profit
        equity[-1] = cash

    # ── 성과 계산 ─────────────────────────────────
    if not trades:
        if not quiet:
            print("  거래 없음")
        return None

    df_trades = pd.DataFrame(trades)
    total    = len(df_trades)
    won      = (df_trades["ror"] > 0).sum()
    lost     = (df_trades["ror"] <= 0).sum()
    win_rate = won / total * 100

    avg_win  = df_trades.loc[df_trades["ror"] > 0,  "ror"].mean() if won  > 0 else 0
    avg_loss = df_trades.loc[df_trades["ror"] <= 0, "ror"].mean() if lost > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    ema_trades = (df_trades["mode"] == "ema").sum()
    vb_trades  = (df_trades["mode"] == "vb").sum()

    equity_arr = np.array(equity)
    final = equity_arr[-1]
    ror   = (final - INITIAL_CASH) / INITIAL_CASH * 100

    returns = pd.Series(equity_arr).pct_change().dropna()
    sharpe  = (returns.mean() / returns.std() * np.sqrt(8760)) if returns.std() > 0 else 0

    running_max = np.maximum.accumulate(equity_arr)
    dd  = (equity_arr - running_max) / running_max * 100
    mdd = dd.min()

    df_trades["hold_h"] = df_trades.apply(
        lambda r: (r["exit_time"] - r["entry_time"]).total_seconds() / 3600
        if pd.notna(r.get("exit_time")) else 0, axis=1
    )
    avg_hold = df_trades["hold_h"].mean()

    if not quiet:
        print(f"\n  데이터: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉)")
        print(f"  레짐:   추세 {(df['regime']=='trend').mean()*100:.0f}%  /  횡보 {(df['regime']=='ranging').mean()*100:.0f}%")
        print(f"  수수료: {COMMISSION*100:.2f}% + 슬리피지: {SLIPPAGE*100:.2f}% (편도)")
        print(f"\n  총 거래:    {total}회  (EMA {ema_trades} / VB {vb_trades})")
        print(f"              롱 {(df_trades['side']=='long').sum()} / 숏 {(df_trades['side']=='short').sum()}")
        print(f"  승률:       {win_rate:.1f}%  (수익 {won} / 손실 {lost})")
        print(f"  P/L 비:     {pl_ratio:.2f}  (avg win {avg_win:.2f}% / avg loss {avg_loss:.2f}%)")
        print(f"  평균 보유:  {avg_hold:.1f}h ({avg_hold/24:.1f}일)")
        print(f"\n  ROR:        {ror:+.2f}%")
        print(f"  Sharpe:     {sharpe:.2f}")
        print(f"  MDD:        {mdd:.2f}%")
        print(f"  최종 자본:  ${final:,.0f}  (초기 ${INITIAL_CASH:,.0f})")

        eq_series = pd.Series(equity_arr, index=df.index)
        prev_val  = INITIAL_CASH
        print(f"\n  연도별 수익:")
        for year, grp in eq_series.groupby(eq_series.index.year):
            end_val = grp.iloc[-1]
            yr  = (end_val - prev_val) / prev_val * 100
            bar = "█" * int(abs(yr) / 5) if abs(yr) < 200 else "█" * 40
            sign = "+" if yr >= 0 else ""
            print(f"    {year}: {sign}{yr:6.1f}%  {bar}")
            prev_val = end_val

        if verbose and total <= 100:
            print(f"\n  거래 목록:")
            for _, t in df_trades.iterrows():
                print(f"    {t['mode']:3}/{t['side']:5} | {t['entry_time']} | {t['ror']:+.2f}%")

    return {
        "coin": coin.upper(), "vb_k": vb_k, "vb_min_range": vb_min_range_pct,
        "ror": ror, "sharpe": sharpe, "mdd": mdd,
        "trades": total, "ema_trades": ema_trades, "vb_trades": vb_trades,
        "win_rate": win_rate, "pl_ratio": pl_ratio,
        "avg_hold_h": avg_hold, "final": final,
    }


# ─────────────────────────────────────────
# VB 파라미터 최적화
# ─────────────────────────────────────────
VB_K_GRID         = [0.2, 0.25, 0.3, 0.4, 0.5, 0.6]
VB_MIN_RANGE_GRID = [0.1, 0.2, 0.3, 0.5]


def optimize_vb(coin: str = "bnb", fast: int = 9, slow: int = 21):
    total_runs = len(VB_K_GRID) * len(VB_MIN_RANGE_GRID)
    print(f"\n{'='*60}")
    print(f"  VB 파라미터 최적화 — {coin.upper()}  ({total_runs}개 조합)")
    print(f"{'='*60}")

    results = []
    for i, (k, min_r) in enumerate(iterproduct(VB_K_GRID, VB_MIN_RANGE_GRID), 1):
        r = run_backtest(coin, fast, slow, vb_k=k, vb_min_range_pct=min_r, quiet=True)
        if r:
            results.append(r)
        pct = i / total_runs * 100
        print(f"  [{i:2d}/{total_runs}] VB_K={k:.2f}  MinRange={min_r:.1f}%"
              f"  → ROR {r['ror']:+.1f}%  Sharpe {r['sharpe']:.2f}  MDD {r['mdd']:.1f}%"
              if r else
              f"  [{i:2d}/{total_runs}] VB_K={k:.2f}  MinRange={min_r:.1f}%  → 거래없음")

    if not results:
        print("  최적화 결과 없음")
        return None

    # Sharpe 기준 정렬
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n  ── 상위 5개 결과 (Sharpe 기준) ──")
    print(f"  {'VB_K':>6}  {'MinRange':>9}  {'ROR':>8}  {'Sharpe':>7}  {'MDD':>7}  {'EMA거래':>6}  {'VB거래':>6}")
    print(f"  {'─'*60}")
    for r in results[:5]:
        print(f"  {r['vb_k']:>6.2f}  {r['vb_min_range']:>9.1f}  "
              f"{r['ror']:>+8.1f}%  {r['sharpe']:>7.2f}  "
              f"{r['mdd']:>6.1f}%  {r['ema_trades']:>6}  {r['vb_trades']:>6}")

    best = results[0]
    print(f"\n  ★ 최적 파라미터: VB_K={best['vb_k']}  VB_MIN_RANGE={best['vb_min_range']}%")
    print(f"    ROR {best['ror']:+.2f}%  Sharpe {best['sharpe']:.2f}  MDD {best['mdd']:.2f}%")

    return best


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin",        default="bnb")
    parser.add_argument("--fast",        type=int,   default=9)
    parser.add_argument("--slow",        type=int,   default=21)
    parser.add_argument("--vb_k",        type=float, default=0.3)
    parser.add_argument("--vb_min_range",type=float, default=0.3)
    parser.add_argument("--optimize",    action="store_true")
    parser.add_argument("--verbose",     action="store_true")
    args = parser.parse_args()

    if args.optimize:
        best = optimize_vb(args.coin, args.fast, args.slow)
        if best:
            print(f"\n  ── 최적 파라미터로 전체 결과 재확인 ──")
            run_backtest(args.coin, args.fast, args.slow,
                         vb_k=best["vb_k"],
                         vb_min_range_pct=best["vb_min_range"],
                         verbose=args.verbose)
    else:
        run_backtest(args.coin, args.fast, args.slow,
                     vb_k=args.vb_k,
                     vb_min_range_pct=args.vb_min_range,
                     verbose=args.verbose)
