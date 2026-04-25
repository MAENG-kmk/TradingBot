# backtestStrategy/DogeMultiTFBacktest.py
"""
DOGE 150x 레버리지 멀티타임프레임 추세추종 백테스터
- EMA 9/21 정렬: 1h, 15m, 5m, 1m 모두 같은 방향
- 진입 트리거: 1m 골든크로스(롱) / 데드크로스(숏)
- 손절: 강제청산 (±1/leverage 이동)
- 익절: tp_pct 파라미터
"""
import pandas as pd
import numpy as np


def load_and_compute_signals(csv_path: str) -> pd.DataFrame:
    """
    1m CSV를 로드하고 MTF EMA 정렬 신호를 계산한다.
    높은 TF EMA는 .shift(1) 후 ffill — 이전 완성봉 기준 (lookahead 방지)
    """
    df = pd.read_csv(csv_path, parse_dates=['Date'])
    df = df.set_index('Date').sort_index()
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

    # ── 1m EMA ────────────────────────────────────────────────
    df['ema9_1m']  = df['Close'].ewm(span=9,  adjust=False).mean()
    df['ema21_1m'] = df['Close'].ewm(span=21, adjust=False).mean()

    # ── 5m EMA (이전 완성봉 기준) ─────────────────────────────
    df_5m = df['Close'].resample('5min').last().to_frame('Close')
    df_5m['ema9']  = df_5m['Close'].ewm(span=9,  adjust=False).mean().shift(1)
    df_5m['ema21'] = df_5m['Close'].ewm(span=21, adjust=False).mean().shift(1)
    df = df.join(df_5m[['ema9', 'ema21']].rename(columns={'ema9': 'ema9_5m', 'ema21': 'ema21_5m'}))
    df[['ema9_5m', 'ema21_5m']] = df[['ema9_5m', 'ema21_5m']].ffill()

    # ── 15m EMA ───────────────────────────────────────────────
    df_15m = df['Close'].resample('15min').last().to_frame('Close')
    df_15m['ema9']  = df_15m['Close'].ewm(span=9,  adjust=False).mean().shift(1)
    df_15m['ema21'] = df_15m['Close'].ewm(span=21, adjust=False).mean().shift(1)
    df = df.join(df_15m[['ema9', 'ema21']].rename(columns={'ema9': 'ema9_15m', 'ema21': 'ema21_15m'}))
    df[['ema9_15m', 'ema21_15m']] = df[['ema9_15m', 'ema21_15m']].ffill()

    # ── 1h EMA ────────────────────────────────────────────────
    df_1h = df['Close'].resample('1h').last().to_frame('Close')
    df_1h['ema9']  = df_1h['Close'].ewm(span=9,  adjust=False).mean().shift(1)
    df_1h['ema21'] = df_1h['Close'].ewm(span=21, adjust=False).mean().shift(1)
    df = df.join(df_1h[['ema9', 'ema21']].rename(columns={'ema9': 'ema9_1h', 'ema21': 'ema21_1h'}))
    df[['ema9_1h', 'ema21_1h']] = df[['ema9_1h', 'ema21_1h']].ffill()

    df = df.dropna()

    # ── 방향 정렬 플래그 ──────────────────────────────────────
    bull_1m  = df['ema9_1m']  > df['ema21_1m']
    bull_5m  = df['ema9_5m']  > df['ema21_5m']
    bull_15m = df['ema9_15m'] > df['ema21_15m']
    bull_1h  = df['ema9_1h']  > df['ema21_1h']

    all_bull = bull_1m & bull_5m & bull_15m & bull_1h
    all_bear = ~bull_1m & ~bull_5m & ~bull_15m & ~bull_1h

    # ── 1m 크로스 ─────────────────────────────────────────────
    prev_bull = bull_1m.shift(1).fillna(False)
    cross_up   = bull_1m & ~prev_bull     # 골든크로스
    cross_down = ~bull_1m & prev_bull     # 데드크로스

    df['long_signal']  = (all_bull & cross_up).astype(np.int8)
    df['short_signal'] = (all_bear & cross_down).astype(np.int8)

    return df


def run_backtest(
    df: pd.DataFrame,
    tp_pct: float,          # 익절 목표 (%, 예: 1.0 = 1%)
    initial_capital: float = 10_000.0,
    leverage: int = 150,
    margin_pct: float = 0.01,       # 시드 대비 증거금 비율
    commission_pct: float = 0.0004, # 편도 수수료 (0.04%)
    track_equity: bool = False,
) -> dict:
    """
    단일 TP% 값으로 백테스트를 실행하고 결과를 반환한다.
    진입가의 1/leverage 역방향 이동 시 강제청산.
    """
    tp_frac  = tp_pct / 100.0
    liq_frac = 1.0 / leverage         # ~0.00667

    closes = df['Close'].values
    highs  = df['High'].values
    lows   = df['Low'].values
    long_s = df['long_signal'].values
    short_s = df['short_signal'].values
    n = len(closes)

    capital    = initial_capital
    in_pos     = False
    direction  = 0
    liq_price  = 0.0
    tp_price   = 0.0
    margin     = 0.0
    notional   = 0.0
    n_tp       = 0
    n_liq      = 0
    peak_cap   = capital
    max_dd     = 0.0

    equity_curve = [capital] if track_equity else None

    i = 0
    while i < n:
        if not in_pos:
            if long_s[i]:
                direction = 1
            elif short_s[i]:
                direction = -1
            else:
                if track_equity:
                    equity_curve.append(capital)
                i += 1
                continue

            margin   = capital * margin_pct
            notional = margin * leverage
            entry    = closes[i]
            capital -= notional * commission_pct  # 진입 수수료

            if direction == 1:
                liq_price = entry * (1.0 - liq_frac)
                tp_price  = entry * (1.0 + tp_frac)
            else:
                liq_price = entry * (1.0 + liq_frac)
                tp_price  = entry * (1.0 - tp_frac)

            in_pos = True
            if track_equity:
                equity_curve.append(capital)
            i += 1

        else:
            hi = highs[i]
            lo = lows[i]

            if direction == 1:
                liq_hit = lo <= liq_price
                tp_hit  = hi >= tp_price
            else:
                liq_hit = hi >= liq_price
                tp_hit  = lo <= tp_price

            # 같은 캔들에서 둘 다 터치 → 강제청산 우선 (보수적)
            if liq_hit:
                capital -= margin
                n_liq += 1
                in_pos = False
            elif tp_hit:
                profit  = notional * tp_frac - notional * commission_pct
                capital += profit
                n_tp += 1
                in_pos = False

            # 최대 낙폭 추적
            if capital > peak_cap:
                peak_cap = capital
            dd = (peak_cap - capital) / peak_cap * 100
            if dd > max_dd:
                max_dd = dd

            if track_equity:
                equity_curve.append(capital)
            i += 1

    total = n_tp + n_liq
    ror   = (capital - initial_capital) / initial_capital * 100

    result = {
        'tp_pct':    tp_pct,
        'ror':       ror,
        'final':     capital,
        'total':     total,
        'n_tp':      n_tp,
        'n_liq':     n_liq,
        'win_rate':  n_tp / total * 100 if total > 0 else 0.0,
        'mdd':       max_dd,
    }
    if track_equity:
        result['equity'] = equity_curve
    return result
