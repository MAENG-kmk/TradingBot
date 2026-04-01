"""
BTC-ETH 페어 트레이딩 백테스트

공적분(Cointegration) 관계를 이용한 통계적 차익거래:
  1. Rolling OLS로 헷지 비율 β 추정: log(BTC) = α + β×log(ETH) + ε
  2. 스프레드 = log(BTC) - β×log(ETH) - α
  3. Z-score = (스프레드 - 이동평균) / 이동표준편차

진입:
  Z > +entry_z  → BTC 숏 + ETH 롱  (BTC 상대적 고평가)
  Z < -entry_z  → BTC 롱 + ETH 숏  (BTC 상대적 저평가)

청산:
  |Z| < exit_z  → 스프레드 평균 회귀 → 익절
  |Z| > stop_z  → 스프레드 확산 지속 → 손절

사용법:
  python backtest_pair.py
"""

import sys
import os
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

# ── 파라미터 ───────────────────────────────────────────────────
LOOKBACK    = 60      # Rolling OLS·Z-score 윈도우 (60봉 = 10일)
ENTRY_Z     = 2.0     # 진입 Z-score 임계값
EXIT_Z      = 0.5     # 청산 Z-score 임계값
STOP_Z      = 3.5     # 손절 Z-score 임계값
COMMISSION  = 0.0005  # 편도 수수료 (0.05%)
INITIAL_CASH = 100_000.0
LEG_RATIO   = 0.45    # 레그당 자본 비율 (총 90% 투입)


# ── 데이터 로드 ────────────────────────────────────────────────
def load_price(path, col='Close'):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df[col].astype(float)


btc = load_price('backtestDatas/btcusdt_4h.csv')
eth = load_price('backtestDatas/ethusdt_4h.csv')

df = pd.DataFrame({'BTC': btc, 'ETH': eth}).dropna()
df.sort_index(inplace=True)

print(f"데이터: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df)}봉)")


# ── 공적분 검정 ────────────────────────────────────────────────
log_btc = np.log(df['BTC'])
log_eth = np.log(df['ETH'])

score, pvalue, _ = coint(log_btc, log_eth)
print(f"\n[공적분 검정 (Engle-Granger)]")
print(f"  검정통계량: {score:.4f}")
print(f"  p-value   : {pvalue:.4f}  {'✅ 공적분 확인 (p<0.05)' if pvalue < 0.05 else '⚠️  공적분 불확실'}")


# ── Rolling OLS 헷지 비율 추정 ─────────────────────────────────
def rolling_ols(y, x, window):
    """
    y = α + β·x 에서 Rolling OLS로 α, β 계산
    Cov(x,y)/Var(x) 벡터화 구현 → 빠른 계산
    """
    xy    = (x * y).rolling(window).mean()
    xx    = (x * x).rolling(window).mean()
    x_mu  = x.rolling(window).mean()
    y_mu  = y.rolling(window).mean()

    beta  = (xy - x_mu * y_mu) / (xx - x_mu ** 2)
    alpha = y_mu - beta * x_mu
    return alpha, beta


alpha, beta = rolling_ols(log_btc, log_eth, LOOKBACK)
spread = log_btc - beta * log_eth - alpha

# Rolling Z-score
sp_mu  = spread.rolling(LOOKBACK).mean()
sp_std = spread.rolling(LOOKBACK).std()
zscore = (spread - sp_mu) / sp_std


# ── 백테스트 시뮬레이션 ────────────────────────────────────────
cash     = INITIAL_CASH
btc_qty  = 0.0    # BTC 보유량 (음수 = 숏)
eth_qty  = 0.0    # ETH 보유량 (음수 = 숏)
position = 0      # 0: 없음, 1: BTC롱/ETH숏, -1: BTC숏/ETH롱

entry_z     = 0.0
entry_idx   = None

portfolio   = []
trades      = []

start_idx = LOOKBACK * 2  # 충분한 워밍업 후 시작

for i in range(len(df)):
    row       = df.iloc[i]
    btc_price = row['BTC']
    eth_price = row['ETH']
    z         = zscore.iloc[i]
    dt        = df.index[i]

    port_val = cash + btc_qty * btc_price + eth_qty * eth_price
    portfolio.append({'dt': dt, 'value': port_val, 'zscore': z})

    if i < start_idx or np.isnan(z) or np.isnan(beta.iloc[i]):
        continue

    # ── 청산 ──────────────────────────────────────────────────
    if position != 0:
        exit_signal = False
        exit_reason = ''

        if position == -1:   # BTC숏/ETH롱 → Z가 내려오면 청산
            if z <= EXIT_Z:
                exit_signal, exit_reason = True, '회귀청산'
            elif z >= STOP_Z:
                exit_signal, exit_reason = True, '손절'
        else:                # BTC롱/ETH숏 → Z가 올라오면 청산
            if z >= -EXIT_Z:
                exit_signal, exit_reason = True, '회귀청산'
            elif z <= -STOP_Z:
                exit_signal, exit_reason = True, '손절'

        if exit_signal:
            btc_close_val = btc_qty * btc_price
            eth_close_val = eth_qty * eth_price
            comm = (abs(btc_close_val) + abs(eth_close_val)) * COMMISSION
            pnl  = btc_close_val + eth_close_val - comm

            trades.append({
                'entry_dt' : entry_idx,
                'exit_dt'  : dt,
                'direction': 'BTC숏/ETH롱' if position == -1 else 'BTC롱/ETH숏',
                'entry_z'  : entry_z,
                'exit_z'   : z,
                'pnl'      : pnl,
                'reason'   : exit_reason,
            })

            cash    += pnl
            btc_qty  = 0.0
            eth_qty  = 0.0
            position = 0

    # ── 진입 ──────────────────────────────────────────────────
    if position == 0:
        port_val = cash  # 포지션 없는 상태
        leg_size = port_val * LEG_RATIO

        if z > ENTRY_Z:
            # BTC 고평가 → BTC 숏, ETH 롱
            btc_qty  = -leg_size / btc_price
            eth_qty  =  leg_size / eth_price
            comm     = leg_size * 2 * COMMISSION
            cash    -= comm
            position = -1
            entry_z  = z
            entry_idx = dt

        elif z < -ENTRY_Z:
            # BTC 저평가 → BTC 롱, ETH 숏
            btc_qty  =  leg_size / btc_price
            eth_qty  = -leg_size / eth_price
            comm     = leg_size * 2 * COMMISSION
            cash    -= comm
            position = 1
            entry_z  = z
            entry_idx = dt


# ── 잔여 포지션 강제 청산 ──────────────────────────────────────
if position != 0:
    btc_price = df['BTC'].iloc[-1]
    eth_price = df['ETH'].iloc[-1]
    btc_close_val = btc_qty * btc_price
    eth_close_val = eth_qty * eth_price
    comm = (abs(btc_close_val) + abs(eth_close_val)) * COMMISSION
    pnl  = btc_close_val + eth_close_val - comm
    cash += pnl
    trades.append({
        'entry_dt' : entry_idx,
        'exit_dt'  : df.index[-1],
        'direction': 'BTC숏/ETH롱' if position == -1 else 'BTC롱/ETH숏',
        'entry_z'  : entry_z,
        'exit_z'   : zscore.iloc[-1],
        'pnl'      : pnl,
        'reason'   : '강제청산',
    })


# ── 결과 집계 ──────────────────────────────────────────────────
port_df  = pd.DataFrame(portfolio).set_index('dt')
trade_df = pd.DataFrame(trades)

final_val = cash + btc_qty * df['BTC'].iloc[-1] + eth_qty * df['ETH'].iloc[-1]
ror       = (final_val - INITIAL_CASH) / INITIAL_CASH * 100

# MDD 계산
pv        = port_df['value']
roll_max  = pv.cummax()
drawdown  = (pv - roll_max) / roll_max * 100
mdd       = drawdown.min()

# 거래 통계
total_trades = len(trade_df)
if total_trades > 0:
    won      = (trade_df['pnl'] > 0).sum()
    lost     = (trade_df['pnl'] <= 0).sum()
    win_rate = won / total_trades * 100
    avg_win  = trade_df.loc[trade_df['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    avg_loss = trade_df.loc[trade_df['pnl'] <= 0, 'pnl'].mean() if lost > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    # 홀딩 기간 (봉)
    trade_df['hold_bars'] = trade_df.apply(
        lambda r: len(df[r['entry_dt']:r['exit_dt']]), axis=1
    )
    avg_hold = trade_df['hold_bars'].mean()

    # 청산 이유 분포
    reason_cnt = trade_df['reason'].value_counts()

    # Sharpe (봉 단위)
    pv_ret = pv.pct_change().dropna()
    sharpe = (pv_ret.mean() / pv_ret.std() * np.sqrt(365 * 6)) if pv_ret.std() > 0 else 0


# ── 출력 ───────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  BTC-ETH 페어 트레이딩 백테스트 결과")
print(f"  (4h봉 | LOOKBACK={LOOKBACK} | EntryZ={ENTRY_Z} | ExitZ={EXIT_Z} | StopZ={STOP_Z})")
print(f"{'='*60}")
print(f"  초기 자본  : ${INITIAL_CASH:>12,.2f}")
print(f"  최종 자본  : ${final_val:>12,.2f}")
print(f"  ROR        : {ror:>+10.2f}%")
print(f"  Sharpe     : {sharpe:>10.2f}")
print(f"  MDD        : {mdd:>10.2f}%")
print(f"{'='*60}")
if total_trades > 0:
    print(f"  총 거래    : {total_trades}회  (수익: {won}, 손실: {lost})")
    print(f"  승률       : {win_rate:.1f}%")
    print(f"  P/L 비     : {pl_ratio:.2f}")
    print(f"  평균 수익  : ${avg_win:>10,.2f}")
    print(f"  평균 손실  : ${avg_loss:>10,.2f}")
    print(f"  평균 보유  : {avg_hold:.1f}봉 ({avg_hold*4:.0f}h)")
    print(f"\n  청산 이유:")
    for reason, cnt in reason_cnt.items():
        print(f"    {reason}: {cnt}회")

print(f"{'='*60}")

# 방향별 성과
if total_trades > 0:
    print(f"\n  방향별 성과:")
    for direction in trade_df['direction'].unique():
        sub = trade_df[trade_df['direction'] == direction]
        w   = (sub['pnl'] > 0).sum()
        print(f"    {direction}: {len(sub)}회 | 승률 {w/len(sub)*100:.1f}% | "
              f"합계 ${sub['pnl'].sum():>+,.0f}")

print(f"{'='*60}")
