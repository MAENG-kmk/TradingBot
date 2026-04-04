"""
레짐 필터 비교 백테스트 — 변동성 돌파 (4H close 모드)

레짐 필터 종류:
  none      : 필터 없음 (기준선)
  adx       : ADX > threshold → 추세장에서만 진입
  atr_pct   : ATR > 하위 N% 분위 → 충분한 변동성에서만 진입
  hurst     : Hurst 지수 > 0.5 → 추세 지속성 있는 구간에서만 진입
  combined  : adx + atr_pct 동시 충족

사용법:
  python backtest_regime.py              # 전체 코인 요약
  python backtest_regime.py --coin doge  # 단일 코인 상세
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import pandas as pd
import numpy as np

COMMISSION = 0.0005
INITIAL    = 100_000.0
POSITION_PCT = 0.10    # 10% 포지션 (현실적 수치)

# VB 고정 파라미터 (DOGE 최적값 기준)
VB_K         = 0.3
MIN_RANGE_PCT = 0.3


# ── 데이터 로드 ──────────────────────────────────────────────────
def load_ohlcv(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    df = df[['Open','High','Low','Close','Volume']].astype(float).sort_index()
    return df


# ── 지표 계산 ────────────────────────────────────────────────────

def calc_adx(h, l, c, period=14):
    """ADX (Average Directional Index)"""
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    up   = h - h.shift(1)
    down = l.shift(1) - l

    plus_dm  = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)

    plus_di  = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx


def calc_atr(h, l, c, period=14):
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def calc_hurst(series, min_n=10):
    """
    단순 R/S 분석 기반 Hurst 지수 추정
    series: 가격 시계열 (길이 window)
    반환: H (0~1), H>0.5 추세, H<0.5 평균회귀
    """
    n = len(series)
    if n < min_n:
        return 0.5

    lags  = []
    rs_vals = []
    for lag in range(min_n, n // 2 + 1, max(1, (n // 2 - min_n) // 8)):
        chunks = [series[j:j+lag] for j in range(0, n - lag + 1, lag)]
        if len(chunks) < 2:
            continue
        rs_list = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            mean  = np.mean(chunk)
            dev   = np.cumsum(chunk - mean)
            r     = dev.max() - dev.min()
            s     = np.std(chunk, ddof=1)
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            lags.append(np.log(lag))
            rs_vals.append(np.log(np.mean(rs_list)))

    if len(lags) < 3:
        return 0.5
    h, _ = np.polyfit(lags, rs_vals, 1)
    return float(np.clip(h, 0.0, 1.0))


def calc_rolling_hurst(c, window=60, step=1):
    """롤링 Hurst 지수 시리즈 (느림 — 캐싱 방식)"""
    values = np.full(len(c), np.nan)
    arr = c.values
    for i in range(window - 1, len(arr), step):
        h = calc_hurst(arr[i - window + 1: i + 1])
        # step 구간 전체에 동일 값 채움 (보간)
        start = max(0, i - step + 1)
        values[start: i + 1] = h
    s = pd.Series(values, index=c.index)
    s = s.ffill()
    return s


# ── 핵심 시뮬레이션 ──────────────────────────────────────────────

def simulate(df, regime='none',
             adx_period=14, adx_min=20,
             atr_period=14, atr_pct=25,
             hurst_window=60, hurst_min=0.55):
    """
    Parameters
    ----------
    regime     : 'none' | 'adx' | 'atr_pct' | 'hurst' | 'combined'
    adx_min    : ADX 최소값 (이상이어야 추세장)
    atr_pct    : ATR 하위 N% 분위 이상이어야 진입 허용
    hurst_window: 롤링 Hurst 계산 윈도우 (봉 수)
    hurst_min  : Hurst 최소값 (이상이어야 추세 지속성)
    """
    o = df['Open']; h = df['High']; l = df['Low']; c = df['Close']

    prev_range = (h - l).shift(1)
    prev_close = c.shift(1)
    range_pct  = prev_range / prev_close * 100

    long_trig  = o + VB_K * prev_range
    short_trig = o - VB_K * prev_range

    # 레짐 지표 사전 계산
    adx_series = calc_adx(h, l, c, adx_period)
    atr_series = calc_atr(h, l, c, atr_period)
    atr_roll_pct = atr_series.rolling(252).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    )  # 롤링 분위수

    if regime in ('hurst', 'combined_hurst'):
        print(f"    Hurst 계산 중 (window={hurst_window})...", end=' ', flush=True)
        hurst_series = calc_rolling_hurst(c, window=hurst_window)
        print("완료")
    else:
        hurst_series = None

    warmup = max(adx_period * 2, atr_period * 2, 252, 2)

    cash   = INITIAL
    equity = []
    trades = []

    for i in range(warmup, len(df) - 1):
        pr    = prev_range.iloc[i]
        rng_p = range_pct.iloc[i]
        lt    = long_trig.iloc[i]
        st    = short_trig.iloc[i]
        hi    = h.iloc[i]; lo = l.iloc[i]
        cl    = c.iloc[i]; op = o.iloc[i]
        next_open = o.iloc[i + 1]

        # 기본 VB 조건
        if pd.isna(pr) or pr <= 0 or rng_p < MIN_RANGE_PCT:
            equity.append(cash)
            continue

        long_ok  = hi >= lt and lt > op
        short_ok = lo <= st and st < op
        if long_ok and short_ok:
            equity.append(cash)
            continue

        dir_now = 'long' if long_ok else ('short' if short_ok else None)
        if dir_now is None:
            equity.append(cash)
            continue

        # ── 레짐 필터 적용 ────────────────────────────────────
        adx_val   = adx_series.iloc[i]
        atr_p_val = atr_roll_pct.iloc[i]

        if regime == 'adx':
            if pd.isna(adx_val) or adx_val < adx_min:
                equity.append(cash)
                continue

        elif regime == 'atr_pct':
            if pd.isna(atr_p_val) or atr_p_val < atr_pct:
                equity.append(cash)
                continue

        elif regime == 'hurst':
            h_val = hurst_series.iloc[i] if hurst_series is not None else 0.5
            if pd.isna(h_val) or h_val < hurst_min:
                equity.append(cash)
                continue

        elif regime == 'combined':
            if pd.isna(adx_val) or adx_val < adx_min:
                equity.append(cash)
                continue
            if pd.isna(atr_p_val) or atr_p_val < atr_pct:
                equity.append(cash)
                continue

        # ── 진입 & close 청산 ─────────────────────────────────
        entry  = lt if dir_now == 'long' else st
        exit_p = cl   # close 모드 고정

        size   = cash * POSITION_PCT / entry
        comm   = (entry + exit_p) * size * COMMISSION
        pnl    = ((exit_p - entry) if dir_now == 'long' else (entry - exit_p)) * size - comm
        cash  += pnl
        trades.append(dict(
            dt=df.index[i], dir=dir_now,
            entry=entry, exit_p=exit_p, pnl=pnl,
        ))
        equity.append(cash)

    if not trades:
        return None

    trade_df = pd.DataFrame(trades)
    eq       = pd.Series(equity)

    total = len(trade_df)
    won   = (trade_df['pnl'] > 0).sum()
    lost  = (trade_df['pnl'] <= 0).sum()
    avg_p = trade_df.loc[trade_df['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    avg_l = trade_df.loc[trade_df['pnl'] <= 0, 'pnl'].mean() if lost > 0 else 0
    pl    = abs(avg_p / avg_l) if avg_l != 0 else 0

    final  = cash
    ror    = (final - INITIAL) / INITIAL * 100
    roll_max = eq.cummax()
    mdd    = ((eq - roll_max) / roll_max * 100).min()
    ret    = eq.pct_change().dropna()
    sharpe = (ret.mean() / ret.std() * np.sqrt(365 * 6)) if ret.std() > 0 else 0

    return dict(
        total=total, won=won, lost=lost,
        win_rate=won/total*100,
        pl_ratio=pl, ror=ror, sharpe=sharpe, mdd=mdd,
        avg_win=avg_p, avg_loss=avg_l,
        final=final, trades=trade_df,
    )


# ── 출력 헬퍼 ────────────────────────────────────────────────────

REGIMES = ['none', 'adx', 'atr_pct', 'hurst', 'combined']
REGIME_LABELS = {
    'none'    : '필터없음',
    'adx'     : 'ADX≥20',
    'atr_pct' : 'ATR≥25%',
    'hurst'   : 'Hurst≥0.55',
    'combined': 'ADX+ATR',
}


def print_coin_detail(coin, results):
    print(f"\n{'='*70}")
    print(f"  {coin.upper()}  —  변동성 돌파 Close (k={VB_K}, pos={POSITION_PCT*100:.0f}%)")
    print(f"{'='*70}")
    print(f"  {'레짐':>12}  {'거래':>5}  {'승률':>6}  {'ROR':>8}  "
          f"{'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
    print(f"  {'-'*60}")
    for regime, r in results.items():
        if r is None:
            print(f"  {REGIME_LABELS[regime]:>12}  {'데이터부족':^40}")
            continue
        print(f"  {REGIME_LABELS[regime]:>12}  {r['total']:>5}  "
              f"{r['win_rate']:>5.1f}%  {r['ror']:>+7.1f}%  "
              f"{r['sharpe']:>6.2f}  {r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")
    print(f"{'='*70}")

    # 연도별 성과 (none vs best)
    base = results.get('none')
    if base is None:
        return

    # best = 필터 중 ROR 최고
    best_regime = max(
        [r for r in REGIMES if r != 'none' and results.get(r)],
        key=lambda r: results[r]['ror'],
        default=None
    )
    if best_regime is None:
        return

    best = results[best_regime]
    print(f"\n  연도별 비교: 필터없음 vs {REGIME_LABELS[best_regime]}")
    print(f"  {'년도':<6}  {'없음ROR':>8}  {REGIME_LABELS[best_regime]+' ROR':>12}  "
          f"{'없음거래':>8}  {'필터거래':>8}")
    print(f"  {'-'*55}")

    td_base = base['trades'].copy(); td_base['year'] = td_base['dt'].dt.year
    td_best = best['trades'].copy(); td_best['year'] = td_best['dt'].dt.year
    cumcash_b = INITIAL; cumcash_f = INITIAL
    all_years = sorted(set(td_base['year']) | set(td_best['year']))
    for yr in all_years:
        gb = td_base[td_base['year'] == yr]
        gf = td_best[td_best['year'] == yr]
        ror_b = gb['pnl'].sum() / cumcash_b * 100 if len(gb) > 0 else 0
        ror_f = gf['pnl'].sum() / cumcash_f * 100 if len(gf) > 0 else 0
        cumcash_b += gb['pnl'].sum()
        cumcash_f += gf['pnl'].sum()
        print(f"  {yr:<6}  {ror_b:>+7.1f}%  {ror_f:>+11.1f}%  "
              f"{len(gb):>8}  {len(gf):>8}")


def print_summary_table(all_results):
    """전체 코인 × 레짐 요약 테이블"""
    print(f"\n{'='*80}")
    print(f"  전 코인 레짐 필터 비교 요약  (VB k={VB_K}, pos={POSITION_PCT*100:.0f}%, close모드)")
    print(f"{'='*80}")

    for regime in REGIMES:
        label = REGIME_LABELS[regime]
        print(f"\n  ── {label} ──")
        print(f"  {'코인':<6}  {'거래':>5}  {'승률':>6}  {'ROR':>8}  "
              f"{'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
        print(f"  {'-'*56}")
        for coin, results in all_results.items():
            r = results.get(regime)
            if r is None:
                continue
            print(f"  {coin.upper():<6}  {r['total']:>5}  "
                  f"{r['win_rate']:>5.1f}%  {r['ror']:>+7.1f}%  "
                  f"{r['sharpe']:>6.2f}  {r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")


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
    parser.add_argument('--coin', default='all', help='코인 (btc/eth/.../all)')
    args = parser.parse_args()

    coins = {args.coin: COIN_DATA[args.coin]} if args.coin != 'all' else COIN_DATA

    all_results = {}

    for coin, path in coins.items():
        if not os.path.exists(path):
            print(f"  {coin}: 데이터 없음 ({path})")
            continue

        print(f"\n[{coin.upper()}] 시뮬레이션 중...")
        df = load_ohlcv(path)
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")

        results = {}
        for regime in REGIMES:
            print(f"  레짐={regime}...", end=' ', flush=True)
            r = simulate(df, regime=regime)
            results[regime] = r
            if r:
                print(f"ROR {r['ror']:+.1f}%  거래 {r['total']}회")
            else:
                print("결과없음")

        all_results[coin] = results

        if args.coin != 'all':
            print_coin_detail(coin, results)

    if args.coin == 'all':
        print_summary_table(all_results)

        # 필터 효과 요약
        print(f"\n{'='*80}")
        print(f"  레짐 필터 효과 요약 (필터없음 대비 ROR 차이)")
        print(f"{'='*80}")
        print(f"  {'코인':<6}", end='')
        for regime in REGIMES[1:]:
            print(f"  {REGIME_LABELS[regime]:>11}", end='')
        print()
        print(f"  {'-'*65}")
        for coin, results in all_results.items():
            base_ror = results['none']['ror'] if results.get('none') else 0
            print(f"  {coin.upper():<6}", end='')
            for regime in REGIMES[1:]:
                r = results.get(regime)
                if r:
                    diff = r['ror'] - base_ror
                    mark = '▲' if diff > 0 else '▼'
                    print(f"  {mark}{diff:>+9.1f}%", end='')
                else:
                    print(f"  {'N/A':>11}", end='')
            print()
        print(f"{'='*80}")
