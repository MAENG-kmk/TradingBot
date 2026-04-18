"""
4H 캔들 시간대별 변동성 통계

측정 지표:
  range_pct  : (High - Low) / Open × 100  — 봉 내 가격 범위 %
  body_pct   : |Close - Open| / Open × 100 — 봉 몸통 크기 %
  direction  : +1(양봉) / -1(음봉) 비율
  atr_ratio  : 해당 봉의 range / 직전 20봉 ATR 평균 (상대 변동성)

UTC 4H 캔들 오픈 시각: 00, 04, 08, 12, 16, 20
KST 변환:             09, 13, 17, 21, 01, 05
"""

import os, sys, glob
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

DATA_DIR = 'backtestDatas'
KST_OFFSET = 9  # UTC + 9

# 분석 대상 코인 (4h 파일 기준)
FILES = sorted(glob.glob(os.path.join(DATA_DIR, '*usdt_4h.csv')))
COINS = [os.path.basename(f).replace('usdt_4h.csv', '').upper() for f in FILES]

UTC_SLOTS  = [0, 4, 8, 12, 16, 20]
KST_LABELS = {h: f"UTC {h:02d}시 (KST {(h+KST_OFFSET)%24:02d}시)" for h in UTC_SLOTS}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    for c in ['Open', 'High', 'Low', 'Close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    df['utc_hour'] = df['Date'].dt.hour
    df['kst_hour'] = (df['Date'].dt.hour + KST_OFFSET) % 24
    return df


def calc_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['range_pct'] = (df['High'] - df['Low']) / df['Open'] * 100
    df['body_pct']  = (df['Close'] - df['Open']).abs() / df['Open'] * 100
    df['bull']      = (df['Close'] >= df['Open']).astype(int)

    # ATR 상대 변동성 (직전 20봉 range 평균 대비)
    roll_atr = df['range_pct'].rolling(20, min_periods=5).mean().shift(1)
    df['atr_ratio'] = df['range_pct'] / roll_atr.replace(0, np.nan)

    return df


def hour_stats(df: pd.DataFrame) -> pd.DataFrame:
    grp = df.groupby('utc_hour')
    stats = pd.DataFrame({
        'n':           grp['range_pct'].count(),
        'range_mean':  grp['range_pct'].mean(),
        'range_med':   grp['range_pct'].median(),
        'range_std':   grp['range_pct'].std(),
        'range_90p':   grp['range_pct'].quantile(0.90),
        'body_mean':   grp['body_pct'].mean(),
        'bull_rate':   grp['bull'].mean() * 100,
        'atr_ratio':   grp['atr_ratio'].mean(),
    }).loc[UTC_SLOTS]
    return stats


def print_coin_table(coin: str, stats: pd.DataFrame):
    print(f"\n  ── {coin} ──────────────────────────────────────────────────────")
    print(f"  {'UTC시':>5} {'KST시':>5}  {'N':>5}  "
          f"{'범위평균':>7}  {'범위중간':>7}  {'범위90%':>7}  "
          f"{'몸통평균':>7}  {'양봉비율':>7}  {'상대변동':>7}")
    for utc_h, row in stats.iterrows():
        kst_h = (utc_h + KST_OFFSET) % 24
        bar   = '█' * int(row['range_mean'] / stats['range_mean'].max() * 12)
        print(f"  {utc_h:>4}시 {kst_h:>4}시  {int(row['n']):>5}  "
              f"{row['range_mean']:>6.3f}%  {row['range_med']:>6.3f}%  "
              f"{row['range_90p']:>6.3f}%  {row['body_mean']:>6.3f}%  "
              f"{row['bull_rate']:>6.1f}%  {row['atr_ratio']:>6.3f}  {bar}")


def print_combined(all_stats: dict):
    """전 코인 합산 통계"""
    frames = []
    for coin, stats in all_stats.items():
        s = stats.copy()
        s['coin'] = coin
        frames.append(s)
    combined = pd.concat(frames)

    agg = combined.groupby(combined.index).agg(
        range_mean=('range_mean', 'mean'),
        range_med=('range_med', 'mean'),
        range_90p=('range_90p', 'mean'),
        body_mean=('body_mean', 'mean'),
        bull_rate=('bull_rate', 'mean'),
        atr_ratio=('atr_ratio', 'mean'),
        n=('n', 'sum'),
    ).loc[UTC_SLOTS]

    max_range = agg['range_mean'].max()
    min_range = agg['range_mean'].min()
    rank = agg['range_mean'].rank(ascending=False).astype(int)

    print(f"\n{'='*80}")
    print(f"  전 코인 평균 — 시간대별 변동성 요약")
    print(f"{'='*80}")
    print(f"  {'UTC시':>5} {'KST시':>5}  {'총N':>7}  "
          f"{'범위평균':>7}  {'범위중간':>7}  {'범위90%':>7}  "
          f"{'몸통평균':>7}  {'양봉비율':>7}  {'상대변동':>7}  {'순위':>4}  바")
    print(f"  {'-'*78}")
    for utc_h, row in agg.iterrows():
        kst_h = (utc_h + KST_OFFSET) % 24
        bar_len = int((row['range_mean'] - min_range) / (max_range - min_range + 1e-9) * 20)
        bar = '█' * bar_len
        print(f"  {utc_h:>4}시 {kst_h:>4}시  {int(row['n']):>7}  "
              f"{row['range_mean']:>6.3f}%  {row['range_med']:>6.3f}%  "
              f"{row['range_90p']:>6.3f}%  {row['body_mean']:>6.3f}%  "
              f"{row['bull_rate']:>6.1f}%  {row['atr_ratio']:>6.3f}  "
              f"  #{rank[utc_h]}  {bar}")
    print(f"{'='*80}")

    # 변동성 높은 순 정리
    ranked = agg.sort_values('range_mean', ascending=False)
    print("\n  [변동성 순위 요약]")
    for i, (utc_h, row) in enumerate(ranked.iterrows(), 1):
        kst_h = (utc_h + KST_OFFSET) % 24
        diff_pct = (row['range_mean'] - agg['range_mean'].mean()) / agg['range_mean'].mean() * 100
        print(f"  #{i}  UTC {utc_h:02d}시 (KST {kst_h:02d}시)  "
              f"평균범위 {row['range_mean']:.3f}%  "
              f"(전체평균 대비 {diff_pct:+.1f}%)")


def print_heatmap(all_stats: dict):
    """코인 × 시간대 히트맵 (범위평균 %)"""
    print(f"\n{'='*80}")
    print(f"  변동성 히트맵 — 범위평균% (코인 × UTC 시간대)")
    print(f"{'='*80}")

    header = "  " + f"{'코인':>6}  " + "  ".join(f"UTC{h:02d}(KST{(h+KST_OFFSET)%24:02d})" for h in UTC_SLOTS)
    print(header)
    print(f"  {'-'*78}")

    all_vals = []
    rows_data = {}
    for coin, stats in all_stats.items():
        vals = [stats.loc[h, 'range_mean'] if h in stats.index else 0 for h in UTC_SLOTS]
        rows_data[coin] = vals
        all_vals.extend(vals)

    vmin, vmax = min(all_vals), max(all_vals)

    def shade(v):
        ratio = (v - vmin) / (vmax - vmin + 1e-9)
        if   ratio > 0.75: return '████'
        elif ratio > 0.50: return '▓▓▓▓'
        elif ratio > 0.25: return '░░░░'
        else:              return '    '

    for coin, vals in rows_data.items():
        cells = "   ".join(f"{v:5.3f}{shade(v)}" for v in vals)
        print(f"  {coin:>6}  {cells}")

    print(f"{'='*80}")
    print(f"  ████ 상위25%  ▓▓▓▓ 상위50%  ░░░░ 하위50%")


if __name__ == '__main__':
    all_stats = {}

    print("4H 캔들 시간대별 변동성 분석")
    print(f"대상: {', '.join(COINS)}\n")

    for path, coin in zip(FILES, COINS):
        df   = load(path)
        df   = calc_metrics(df)
        stats = hour_stats(df)
        all_stats[coin] = stats
        print_coin_table(coin, stats)

    print_combined(all_stats)
    print_heatmap(all_stats)
