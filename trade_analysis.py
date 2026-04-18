"""
거래 데이터 패턴 분석 — Trade_History.{모델명}

분석 항목:
  1. 전체 요약 (승률, 총손익, 평균ROR 등)
  2. 코인별 성과
  3. 롱/숏 방향별 성과
  4. 시간대별 패턴 (진입 시각 기준, KST)
  5. 요일별 패턴
  6. 보유 시간 vs 승패
  7. ROR 분포
  8. 연속 승패 분석
  9. 월별 손익 추이
 10. 승리/패배 조건 비교 (진입가, 보유시간, 시간대)
"""

import os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from SecretVariables import MONGODB_URI

MODEL_NAME = 'VB & Bolinger'   # 분석할 컬렉션명
KST = timezone(timedelta(hours=9))

# ── 데이터 로드 ───────────────────────────────────────────────────────
def load_trades(model: str) -> pd.DataFrame:
    client = MongoClient(MONGODB_URI, server_api=ServerApi('1'))
    db     = client.get_database("Trade_History")
    col    = db.get_collection(model)
    docs   = list(col.find({}, {'_id': 0}))
    client.close()

    if not docs:
        raise ValueError(f"컬렉션 '{model}'에 데이터가 없습니다.")

    df = pd.DataFrame(docs)
    print(f"  총 {len(df)}건 로드 완료 (컬렉션: {model})")
    return df


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    # 숫자 변환
    for col in ['profit', 'ror', 'balance']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'enterPrice' in df.columns:
        df['enterPrice'] = pd.to_numeric(df['enterPrice'], errors='coerce')

    # 시간 변환 (KST)
    # enterTime: Binance updateTime = 밀리초 Unix, closeTime: 초 Unix
    if 'enterTime' in df.columns:
        df['enterTime_ms'] = pd.to_numeric(df['enterTime'], errors='coerce')
        df['enter_dt'] = pd.to_datetime(df['enterTime_ms'], unit='ms', utc=True).dt.tz_convert(KST)

    if 'closeTime' in df.columns:
        df['close_dt'] = pd.to_datetime(df['closeTime'], unit='s', utc=True).dt.tz_convert(KST)

    # 보유 시간 (시간 단위)
    if 'enter_dt' in df.columns and 'close_dt' in df.columns:
        df['hold_hours'] = (df['close_dt'] - df['enter_dt']).dt.total_seconds() / 3600

    # 시간대/요일
    if 'enter_dt' in df.columns:
        df['enter_hour'] = df['enter_dt'].dt.hour
        df['enter_weekday'] = df['enter_dt'].dt.day_name()
        df['enter_month'] = df['enter_dt'].dt.to_period('M').astype(str)

    # 승패
    df['win'] = df['profit'] > 0

    return df


# ── 출력 유틸 ─────────────────────────────────────────────────────────
SEP = "=" * 60

def _wr(sub):
    if len(sub) == 0: return 0.0
    return sub['win'].sum() / len(sub) * 100

def _summary_line(sub, label):
    if len(sub) == 0:
        print(f"  {label:20s}: 데이터 없음")
        return
    wr   = _wr(sub)
    pnl  = sub['profit'].sum()
    avg  = sub['ror'].mean()
    best = sub['ror'].max()
    worst= sub['ror'].min()
    print(f"  {label:20s}: {len(sub):3d}건 | 승률 {wr:5.1f}% | "
          f"총손익 {pnl:+8.2f}$ | 평균ROR {avg:+5.2f}% | "
          f"최고 {best:+5.1f}% 최악 {worst:+5.1f}%")


# ── 분석 함수들 ───────────────────────────────────────────────────────
def section_overview(df):
    print(SEP)
    print("  1. 전체 요약")
    print(SEP)
    wins   = df['win'].sum()
    losses = len(df) - wins
    wr     = wins / len(df) * 100
    total_pnl = df['profit'].sum()
    avg_ror   = df['ror'].mean()
    median_ror= df['ror'].median()
    avg_win   = df[df['win']]['ror'].mean() if wins > 0 else 0
    avg_loss  = df[~df['win']]['ror'].mean() if losses > 0 else 0
    rr_ratio  = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    if 'hold_hours' in df.columns:
        avg_hold = df['hold_hours'].median()
    else:
        avg_hold = None

    # 최대 낙폭
    if 'balance' in df.columns:
        bal = df.sort_values('close_dt')['balance'].values if 'close_dt' in df.columns else df['balance'].values
        peak = np.maximum.accumulate(bal)
        mdd  = ((bal - peak) / peak * 100).min()
    else:
        mdd = None

    print(f"  기간     : {df['enter_dt'].min().strftime('%Y-%m-%d') if 'enter_dt' in df.columns else '?'}"
          f" ~ {df['close_dt'].max().strftime('%Y-%m-%d') if 'close_dt' in df.columns else '?'}")
    print(f"  거래 수  : {len(df)}건  ({wins}승 {losses}패)")
    print(f"  승률     : {wr:.1f}%")
    print(f"  총 손익  : {total_pnl:+.2f}$")
    print(f"  평균 ROR : {avg_ror:+.2f}%  (중간값 {median_ror:+.2f}%)")
    print(f"  평균 익절: {avg_win:+.2f}%   평균 손절: {avg_loss:+.2f}%")
    print(f"  손익비   : {rr_ratio:.2f}:1")
    if avg_hold: print(f"  중간 보유: {avg_hold:.1f}h")
    if mdd is not None: print(f"  최대 낙폭: {mdd:.2f}%")


def section_by_coin(df):
    print(f"\n{SEP}")
    print("  2. 코인별 성과")
    print(SEP)
    coins = df['symbol'].unique() if 'symbol' in df.columns else []
    rows = []
    for coin in sorted(coins):
        sub = df[df['symbol'] == coin]
        rows.append((coin, len(sub), _wr(sub), sub['profit'].sum(), sub['ror'].mean()))
    rows.sort(key=lambda x: x[3], reverse=True)
    for coin, n, wr, pnl, avg in rows:
        bar = '█' * int(max(0, pnl) / max(1, max(r[3] for r in rows)) * 20) if pnl > 0 else '░' * int(abs(pnl) / max(1, abs(min(r[3] for r in rows))) * 10)
        print(f"  {coin:12s}: {n:3d}건 | 승률 {wr:5.1f}% | 총손익 {pnl:+8.2f}$ | 평균ROR {avg:+5.2f}% {bar}")


def section_by_side(df):
    print(f"\n{SEP}")
    print("  3. 롱/숏 방향별")
    print(SEP)
    if 'side' not in df.columns:
        print("  side 컬럼 없음")
        return
    for side in ['long', 'short']:
        _summary_line(df[df['side'] == side], side.upper())


def section_by_hour(df):
    print(f"\n{SEP}")
    print("  4. 시간대별 패턴 (KST 진입 기준)")
    print(SEP)
    if 'enter_hour' not in df.columns:
        print("  시간 데이터 없음")
        return

    hour_stats = df.groupby('enter_hour').agg(
        n=('profit', 'count'),
        win_rate=('win', lambda x: x.mean() * 100),
        total_pnl=('profit', 'sum'),
        avg_ror=('ror', 'mean'),
    ).reset_index()

    print(f"  {'시간':>4}  {'건수':>4}  {'승률':>6}  {'총손익':>9}  {'평균ROR':>8}  바")
    for _, row in hour_stats.iterrows():
        bar = '▓' * int(max(0, row['total_pnl']) / max(1, hour_stats['total_pnl'].max()) * 15) if row['total_pnl'] > 0 else '░' * int(abs(min(0, row['total_pnl'])) / max(1, abs(hour_stats['total_pnl'].min())) * 10)
        print(f"  {int(row['enter_hour']):02d}시  {int(row['n']):4d}  {row['win_rate']:6.1f}%  "
              f"{row['total_pnl']:+9.2f}$  {row['avg_ror']:+8.2f}%  {bar}")


def section_by_weekday(df):
    print(f"\n{SEP}")
    print("  5. 요일별 패턴")
    print(SEP)
    if 'enter_weekday' not in df.columns:
        print("  요일 데이터 없음")
        return

    order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    kor   = {'Monday':'월', 'Tuesday':'화', 'Wednesday':'수',
             'Thursday':'목', 'Friday':'금', 'Saturday':'토', 'Sunday':'일'}

    for day in order:
        sub = df[df['enter_weekday'] == day]
        if len(sub) == 0: continue
        _summary_line(sub, kor[day] + '요일')


def section_hold_time(df):
    print(f"\n{SEP}")
    print("  6. 보유 시간 vs 승패")
    print(SEP)
    if 'hold_hours' not in df.columns:
        print("  보유 시간 데이터 없음")
        return

    bins   = [0, 4, 8, 24, 48, 96, 9999]
    labels = ['~4h', '4~8h', '8~24h', '24~48h', '48~96h', '96h+']
    df['hold_bin'] = pd.cut(df['hold_hours'], bins=bins, labels=labels, right=False)

    for label in labels:
        sub = df[df['hold_bin'] == label]
        if len(sub) == 0: continue
        _summary_line(sub, label)


def section_ror_dist(df):
    print(f"\n{SEP}")
    print("  7. ROR 분포")
    print(SEP)
    bins   = [-999, -5, -3, -1, 0, 1, 3, 5, 10, 999]
    labels = ['<-5%', '-5~-3%', '-3~-1%', '-1~0%', '0~1%', '1~3%', '3~5%', '5~10%', '>10%']
    df['ror_bin'] = pd.cut(df['ror'], bins=bins, labels=labels, right=False)

    total = len(df)
    for label in labels:
        sub = df[df['ror_bin'] == label]
        n   = len(sub)
        if n == 0: continue
        bar = '█' * int(n / total * 40)
        print(f"  {label:10s}: {n:3d}건 ({n/total*100:4.1f}%) {bar}")


def section_streak(df):
    print(f"\n{SEP}")
    print("  8. 연속 승패 분석")
    print(SEP)
    if 'close_dt' not in df.columns:
        return
    df_s = df.sort_values('close_dt').reset_index(drop=True)
    results = df_s['win'].tolist()

    max_win = max_loss = cur_win = cur_loss = 0
    streaks_win = []
    streaks_loss = []

    for r in results:
        if r:
            cur_win += 1
            if cur_loss > 0:
                streaks_loss.append(cur_loss)
            cur_loss = 0
            max_win = max(max_win, cur_win)
        else:
            cur_loss += 1
            if cur_win > 0:
                streaks_win.append(cur_win)
            cur_win = 0
            max_loss = max(max_loss, cur_loss)

    if cur_win: streaks_win.append(cur_win)
    if cur_loss: streaks_loss.append(cur_loss)

    print(f"  최장 연승: {max_win}연승")
    print(f"  최장 연패: {max_loss}연패")
    if streaks_win:
        print(f"  평균 연승: {np.mean(streaks_win):.1f}회")
    if streaks_loss:
        print(f"  평균 연패: {np.mean(streaks_loss):.1f}회")


def section_monthly(df):
    print(f"\n{SEP}")
    print("  9. 월별 손익 추이")
    print(SEP)
    if 'enter_month' not in df.columns:
        print("  월 데이터 없음")
        return

    monthly = df.groupby('enter_month').agg(
        n=('profit', 'count'),
        win_rate=('win', lambda x: x.mean() * 100),
        total_pnl=('profit', 'sum'),
    ).reset_index().sort_values('enter_month')

    for _, row in monthly.iterrows():
        sign = '+' if row['total_pnl'] >= 0 else ''
        bar  = '█' * int(abs(row['total_pnl']) / max(1, monthly['total_pnl'].abs().max()) * 20)
        color_bar = bar if row['total_pnl'] >= 0 else f"({bar})"
        print(f"  {row['enter_month']}  {int(row['n']):3d}건 | 승률 {row['win_rate']:5.1f}% | "
              f"{sign}{row['total_pnl']:.2f}$  {color_bar}")


def section_win_loss_compare(df):
    print(f"\n{SEP}")
    print("  10. 익절 vs 손절 조건 비교")
    print(SEP)
    wins_df  = df[df['win']]
    loss_df  = df[~df['win']]

    fields = []
    if 'hold_hours' in df.columns:
        fields.append(('보유 시간(h)', 'hold_hours'))
    if 'enter_hour' in df.columns:
        fields.append(('진입 시간(h)', 'enter_hour'))

    for label, col in fields:
        wm = wins_df[col].median() if len(wins_df) else 0
        lm = loss_df[col].median() if len(loss_df) else 0
        print(f"  {label:15s}: 익절 중간값 {wm:.1f}  |  손절 중간값 {lm:.1f}")

    # 코인별 익절/손절 비율
    print()
    print(f"  {'코인':12s}  {'익절':>5}  {'손절':>5}  {'승률':>6}  {'평균익절ROR':>10}  {'평균손절ROR':>10}")
    if 'symbol' in df.columns:
        for coin in sorted(df['symbol'].unique()):
            sub   = df[df['symbol'] == coin]
            w     = sub[sub['win']]
            l     = sub[~sub['win']]
            wr    = len(w) / len(sub) * 100
            avgw  = w['ror'].mean() if len(w) else 0
            avgl  = l['ror'].mean() if len(l) else 0
            print(f"  {coin:12s}  {len(w):5d}  {len(l):5d}  {wr:6.1f}%  {avgw:+10.2f}%  {avgl:+10.2f}%")


# ── 메인 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=MODEL_NAME, help='분석할 MongoDB 컬렉션명')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  거래 분석: {args.model}")
    print(f"{'='*60}")
    print(f"  데이터 로드 중...")

    df = load_trades(args.model)
    df = preprocess(df)

    print(f"  컬럼: {list(df.columns)}\n")

    section_overview(df)
    section_by_coin(df)
    section_by_side(df)
    section_by_hour(df)
    section_by_weekday(df)
    section_hold_time(df)
    section_ror_dist(df)
    section_streak(df)
    section_monthly(df)
    section_win_loss_compare(df)

    print(f"\n{SEP}")
    print("  분석 완료")
    print(SEP)
