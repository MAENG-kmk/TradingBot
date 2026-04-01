"""
래리 윌리엄즈 변동성 돌파 전략 백테스트 (4H 캔들)

전략 원리 (Larry Williams Volatility Breakout):
  목표 매수가 = 당일 시가 + k × 전일 변동폭(High-Low)
  목표 매도가 = 당일 시가 - k × 전일 변동폭
  → 당일 캔들에서 목표가 터치 시 진입
  → 청산: 동일 캔들 종가 or 다음 캔들 시가

4H 적응:
  "전일" = 직전 4H 캔들 (혹은 직전 24H 일봉 집계)
  모드:
    close     : 진입 캔들 종가에 청산  → pnl = close - trigger
    next_open : 다음 캔들 시가에 청산  → pnl = next_open - trigger
    dual      : 1봉 내 양방향 진입 시 방향성 취소 (보수적)

필터:
  MA(n) 방향 필터, 최소 변동폭 필터, RSI 과매수/과매도 필터

사용법:
  python backtest_volatility_breakout.py
  python backtest_volatility_breakout.py --coin all
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import pandas as pd
import numpy as np


COMMISSION  = 0.0005   # 편도 0.05%
INITIAL     = 100_000.0


# ── 데이터 로드 ─────────────────────────────────────────────────
def load_ohlcv(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    df = df[['Open','High','Low','Close','Volume']].astype(float).sort_index()
    return df


# ── 변동성 돌파 시뮬레이션 (pandas 기반) ────────────────────────
def simulate_vb(df, k=0.5, exit_mode='close',
                ma_period=20, ma_filter=True,
                min_range_pct=0.3,
                allow_long=True, allow_short=True,
                atr_period=7, stop_mult=1.5, target_mult=3.0,
                time_exit=8):
    """
    Parameters
    ----------
    k            : 변동성 돌파 계수 (0.3~0.7)
    exit_mode    : 'close' | 'next_open' | 'atr'
    ma_filter    : True → 롱은 close > MA, 숏은 close < MA
    min_range_pct: 전일 변동폭 / 전일 종가 최소 %
    atr_period   : ATR 계산 기간 (exit_mode='atr' 시 사용)
    stop_mult    : ATR × stop_mult → 손절폭
    target_mult  : ATR × target_mult → 목표폭
    time_exit    : ATR 모드 최대 보유 봉수
    """
    o = df['Open']; h = df['High']; l = df['Low']; c = df['Close']

    # 직전봉 변동폭
    prev_range = (h - l).shift(1)
    prev_close = c.shift(1)
    range_pct  = prev_range / prev_close * 100

    # 트리거 가격
    long_trig  = o + k * prev_range
    short_trig = o - k * prev_range

    # MA 필터
    ma = c.rolling(ma_period).mean()

    # ATR (Wilder 방식)
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/atr_period, adjust=False).mean()

    # 다음봉 시가 (next_open 모드용)
    next_o = o.shift(-1)

    cash      = INITIAL
    equity    = []
    trades    = []

    # ATR 모드 포지션 상태
    in_pos    = False
    direction = None
    entry_p   = 0.0
    stop_p    = 0.0
    target_p  = 0.0
    pos_size  = 0.0
    bars_held = 0
    entry_dt  = None

    for i in range(max(ma_period, atr_period, 2), len(df) - 1):
        pr    = prev_range.iloc[i]
        rng_p = range_pct.iloc[i]
        lt    = long_trig.iloc[i]
        st    = short_trig.iloc[i]
        hi    = h.iloc[i]; lo = l.iloc[i]
        cl    = c.iloc[i]; op = o.iloc[i]
        no    = next_o.iloc[i]
        m     = ma.iloc[i]
        cur_atr = atr.iloc[i]

        # ── ATR 모드: 포지션 관리 ──────────────────────────────
        if exit_mode == 'atr' and in_pos:
            bars_held += 1
            is_long = direction == 'long'

            stop_hit   = lo <= stop_p   if is_long else hi >= stop_p
            target_hit = hi >= target_p if is_long else lo <= target_p
            time_hit   = bars_held >= time_exit

            if stop_hit or target_hit or time_hit:
                if target_hit:
                    exit_p = target_p
                elif stop_hit:
                    exit_p = stop_p
                else:
                    exit_p = cl

                comm  = (entry_p + exit_p) * pos_size * COMMISSION
                pnl   = ((exit_p - entry_p) if is_long else (entry_p - exit_p)) * pos_size - comm
                cash += pnl
                trades.append(dict(
                    dt=entry_dt, dir=direction,
                    entry=entry_p, exit_p=exit_p, pnl=pnl,
                    bars=bars_held,
                    reason='target' if target_hit else ('stop' if stop_hit else 'time'),
                ))
                in_pos = False
            equity.append(cash)
            continue

        # ── 진입 신호 확인 ─────────────────────────────────────
        if pd.isna(pr) or pr <= 0 or rng_p < min_range_pct or pd.isna(m):
            equity.append(cash)
            continue

        long_ok  = allow_long  and hi >= lt and lt > op
        short_ok = allow_short and lo <= st and st < op

        if ma_filter:
            long_ok  = long_ok  and cl > m
            short_ok = short_ok and cl < m

        # 양방향 동시 트리거 → 스킵
        if long_ok and short_ok:
            equity.append(cash)
            continue

        dir_now = 'long' if long_ok else ('short' if short_ok else None)
        if dir_now is None:
            equity.append(cash)
            continue

        entry  = lt if dir_now == 'long' else st

        # ── close / next_open 모드 ─────────────────────────────
        if exit_mode in ('close', 'next_open'):
            exit_p = cl if exit_mode == 'close' else no
            size   = cash * 0.99 / entry
            comm   = (entry + exit_p) * size * COMMISSION
            pnl    = ((exit_p - entry) if dir_now == 'long' else (entry - exit_p)) * size - comm
            cash  += pnl
            trades.append(dict(dt=df.index[i], dir=dir_now,
                               entry=entry, exit_p=exit_p, pnl=pnl, bars=1, reason='close'))
            equity.append(cash)

        # ── ATR 모드 진입 ──────────────────────────────────────
        else:
            size     = cash * 0.99 / entry
            in_pos   = True
            direction= dir_now
            entry_p  = entry
            entry_dt = df.index[i]
            pos_size = size
            bars_held= 0
            if dir_now == 'long':
                stop_p   = entry - cur_atr * stop_mult
                target_p = entry + cur_atr * target_mult
            else:
                stop_p   = entry + cur_atr * stop_mult
                target_p = entry - cur_atr * target_mult
            equity.append(cash)

    if not trades:
        return None

    trade_df = pd.DataFrame(trades)
    eq       = pd.Series(equity)

    total   = len(trade_df)
    won     = (trade_df['pnl'] > 0).sum()
    lost    = (trade_df['pnl'] <= 0).sum()
    avg_p   = trade_df.loc[trade_df['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    avg_l   = trade_df.loc[trade_df['pnl'] <= 0, 'pnl'].mean() if lost > 0 else 0
    pl      = abs(avg_p / avg_l) if avg_l != 0 else 0

    final   = cash
    ror     = (final - INITIAL) / INITIAL * 100

    roll_max = eq.cummax()
    mdd      = ((eq - roll_max) / roll_max * 100).min()

    ret      = eq.pct_change().dropna()
    sharpe   = (ret.mean() / ret.std() * np.sqrt(365 * 6)) if ret.std() > 0 else 0

    return dict(
        total=total, won=won, lost=lost,
        win_rate=won/total*100,
        pl_ratio=pl, ror=ror, sharpe=sharpe, mdd=mdd,
        avg_win=avg_p, avg_loss=avg_l,
        final=final, trades=trade_df,
    )


# ── Grid Search ─────────────────────────────────────────────────
def grid_search(df, exit_modes=('close','next_open'), verbose=False):
    best_all = {}

    for mode in exit_modes:
        results = []
        for k in [0.3, 0.4, 0.5, 0.6, 0.7]:
            for ma_f in [True, False]:
                for min_r in [0.0, 0.3, 0.5, 1.0]:
                    r = simulate_vb(df, k=k, exit_mode=mode,
                                    ma_filter=ma_f, min_range_pct=min_r)
                    if r is None or r['total'] < 20:
                        continue
                    r['k'] = k; r['ma_filter'] = ma_f; r['min_range'] = min_r
                    r['exit_mode'] = mode
                    results.append(r)

        if not results:
            best_all[mode] = None
            continue

        results.sort(key=lambda x: x['ror'], reverse=True)
        best_all[mode] = results[0]

        if verbose:
            print(f"\n  [{mode.upper()}]  상위 결과:")
            print(f"  {'k':>4}  {'MA':>3}  {'range':>6}  {'ROR':>8}  {'Sharpe':>7}  "
                  f"{'MDD':>6}  {'승률':>6}  {'거래':>5}")
            print(f"  {'-'*58}")
            for r in results[:10]:
                print(f"  {r['k']:>4}  {'ON' if r['ma_filter'] else 'OFF':>3}  "
                      f"{r['min_range']:>5.1f}%  "
                      f"{r['ror']:>+7.1f}%  {r['sharpe']:>6.2f}  "
                      f"{r['mdd']:>5.1f}%  {r['win_rate']:>5.1f}%  {r['total']:>4}")

    return best_all


# ── 결과 상세 출력 ───────────────────────────────────────────────
def print_detail(coin, r, mode):
    if r is None:
        return
    print(f"\n{'='*60}")
    print(f"  {coin.upper()} — 변동성 돌파  [{mode.upper()}]")
    print(f"  k={r['k']} | MA={'ON' if r['ma_filter'] else 'OFF'} | "
          f"최소range≥{r['min_range']}%")
    print(f"{'='*60}")
    print(f"  ROR      : {r['ror']:>+10.2f}%")
    print(f"  Sharpe   : {r['sharpe']:>10.2f}")
    print(f"  MDD      : {r['mdd']:>10.2f}%")
    print(f"{'='*60}")
    print(f"  총 거래  : {r['total']}회  (수익: {r['won']}, 손실: {r['lost']})")
    print(f"  승률     : {r['win_rate']:.1f}%")
    print(f"  P/L 비   : {r['pl_ratio']:.2f}")
    print(f"  평균 수익: ${r['avg_win']:>10,.2f}")
    print(f"  평균 손실: ${r['avg_loss']:>10,.2f}")
    print(f"{'='*60}")

    # 연도별 성과
    td = r['trades'].copy()
    td['year'] = td['dt'].dt.year
    print(f"  연도별 성과:")
    cumcash = INITIAL
    for yr, grp in td.groupby('year'):
        yr_pnl = grp['pnl'].sum()
        yr_ror = yr_pnl / cumcash * 100
        cumcash += yr_pnl
        w = (grp['pnl'] > 0).sum()
        print(f"    {yr}: {len(grp):>4}회  승률{w/len(grp)*100:>5.1f}%  "
              f"PnL ${yr_pnl:>+10,.0f}  ROR {yr_ror:>+6.1f}%")
    print(f"{'='*60}")


COIN_DATA = {
    'btc' : 'backtestDatas/btcusdt_4h.csv',
    'eth' : 'backtestDatas/ethusdt_4h.csv',
    'sol' : 'backtestDatas/solusdt_4h.csv',
    'bnb' : 'backtestDatas/bnbusdt_4h.csv',
    'xrp' : 'backtestDatas/xrpusdt_4h.csv',
    'link': 'backtestDatas/linkusdt_4h.csv',
    'doge': 'backtestDatas/dogeusdt_4h.csv',
    'avax': 'backtestDatas/avaxusdt_4h.csv',
    'arb' : 'backtestDatas/arbusdt_4h.csv',
    'aave': 'backtestDatas/aaveusdt_4h.csv',
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--coin', default='btc', help='코인 (btc/eth/.../all)')
    args = parser.parse_args()

    coins = list(COIN_DATA.keys()) if args.coin == 'all' else [args.coin]

    if args.coin != 'all':
        # 단일 코인 상세 분석
        coin = coins[0]
        path = COIN_DATA[coin]
        df = load_ohlcv(path)
        print(f"\n데이터: {df.index[0].date()} ~ {df.index[-1].date()}  "
              f"({len(df):,}봉, {(df.index[-1]-df.index[0]).days}일)")
        best = grid_search(df, exit_modes=('close','next_open'), verbose=True)
        for mode, r in best.items():
            print_detail(coin, r, mode)

    else:
        # 전체 코인 요약
        print(f"\n래리 윌리엄즈 변동성 돌파 — 전 코인 최적 결과")
        for mode in ('close', 'next_open'):
            print(f"\n{'='*72}")
            print(f"  청산 방식: {mode.upper()}")
            print(f"{'='*72}")
            print(f"  {'코인':<6}  {'k':>4}  {'MA':>3}  {'ROR':>8}  "
                  f"{'Sharpe':>7}  {'MDD':>6}  {'승률':>6}  {'거래':>5}")
            print(f"  {'-'*66}")
            for coin, path in COIN_DATA.items():
                if not os.path.exists(path):
                    continue
                df = load_ohlcv(path)
                best = grid_search(df, exit_modes=(mode,))
                r = best.get(mode)
                if r:
                    print(f"  {coin.upper():<6}  {r['k']:>4}  "
                          f"{'ON' if r['ma_filter'] else 'OFF':>3}  "
                          f"{r['ror']:>+7.1f}%  {r['sharpe']:>6.2f}  "
                          f"{r['mdd']:>5.1f}%  {r['win_rate']:>5.1f}%  {r['total']:>4}")
            print(f"  {'='*66}")
