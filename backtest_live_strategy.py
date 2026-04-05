"""
실거래 로직 백테스트 — base_strategy.py 추세추종 + 평균회귀
대상: ETH, SOL, BNB, XRP, LINK, AVAX, ARB, AAVE  (8코인)
  ※ DOGE(VB전략) → backtest_xgb_regime.py
  ※ BTC(SDE전략) → backtest_sde.py

비교 모드:
  ADX 라우팅  : ADX(>threshold) + 기울기 기반 레짐 분기 (기존 폴백 로직)
  XGB 라우팅  : BB+MACD 시그널 결과로 Walk-Forward 학습한 XGBoost 필터
                (VB 모델 재사용 아님 — 이 전략의 시그널로 직접 학습)

진입:
  [ADX] ADX>threshold & |기울기|≥0.05 → 추세추종 / 아니면 → 평균회귀
  [XGB] prob ≥ 0.55 → 추세추종 / prob < 0.55 → 평균회귀
        (MIN_TRAIN=100 시그널 이후 활성화, RETRAIN_EVERY=30마다 재학습)
        (학습 전 구간은 ADX 라우팅으로 폴백)

청산:
  추세추종: 4단계 트레일링 + 시간청산(24h/48h) + 변동성급변(ATR×3.0)
  평균회귀: |Z|<exit_z 수렴 / 목표달성 / 손절 / 시간(반감기×배수)
  OU 피팅: 최근 300봉 한정 (라이브와 동일)

사용법:
  python backtest_live_strategy.py               # 전체 8코인 요약
  python backtest_live_strategy.py --coin eth    # 단일 코인 상세
  python backtest_live_strategy.py --coin eth --plot
  python backtest_live_strategy.py --coin eth --chart-save
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from tools.regime_filter import build_features, FEATURE_NAMES
from tools.ouProcess import fit_ou

# Walk-Forward XGB 파라미터
WF_MIN_TRAIN     = 100   # 학습 시작 최소 시그널 수
WF_RETRAIN_EVERY = 30    # 재학습 주기
WF_THRESHOLD     = 0.55  # 진입 확률 임계값


# ── 공통 설정 ─────────────────────────────────────────────────────
COMMISSION   = 0.0005
INITIAL      = 100_000.0
POSITION_PCT = 0.10       # 총 자본의 10% (base_strategy: total/10)

# base_strategy.py 공통 청산 파라미터 (코인별 오버라이드 없음)
DEFAULT_STOP_LOSS    = -2.5
PHASE2_THRESHOLD     = 3.0
PHASE3_THRESHOLD     = 6.0
BREAKEVEN_STOP       = 0.5
TIME_EXIT_BARS_1     = 6     # 24h = 6봉 (4H)
TIME_EXIT_BARS_2     = 12    # 48h = 12봉
TIME_EXIT_ROR_1      = 1.0
TIME_EXIT_ROR_2      = 2.0
VOLATILITY_SPIKE     = 3.0
MR_SLOPE_THRESHOLD   = 0.05
MR_STOP_LOSS         = -1.5
MR_TIME_HALFLIFE_MULT = 2.5  # 기본값 (aave는 2.0으로 오버라이드)

VOL_PERIOD = 20
VOL_MULT   = 1.5

# VB 파라미터 (횡보장 대체 전략)
VB_K            = 0.3    # 진입 트리거 계수
VB_MIN_RANGE_PCT = 0.3   # 직전봉 범위 최소 % (노이즈 필터)


# ── 코인별 파라미터 (coins/*/strategy.py 와 동일) ─────────────────
#   keys: path, symbol, bb_period, bb_std, rsi_overbuy, rsi_oversell,
#         adx_threshold, default_target_ror, trailing, tight_trailing,
#         mr_enabled, mr_entry_z, mr_exit_z, mr_max_hl, mr_time_mult
COIN_CONFIGS = {
    'eth': dict(
        path='backtestDatas/ethusdt_4h.csv', symbol='ETHUSDT',
        slippage_pct=0.0002,
        bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=20,
        adx_threshold=20, default_target=15.0,
        trailing=0.4, tight_trailing=0.65,
        mr_enabled=True,  mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'sol': dict(
        path='backtestDatas/solusdt_4h.csv', symbol='SOLUSDT',
        slippage_pct=0.0003,
        bb_period=15, bb_std=2.5, rsi_overbuy=80, rsi_oversell=20,
        adx_threshold=15, default_target=7.0,
        trailing=0.4, tight_trailing=0.85,
        mr_enabled=True,  mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=10, mr_time_mult=2.5,
    ),
    'bnb': dict(
        path='backtestDatas/bnbusdt_4h.csv', symbol='BNBUSDT',
        slippage_pct=0.0003,
        bb_period=20, bb_std=2.0, rsi_overbuy=70, rsi_oversell=30,
        adx_threshold=20, default_target=10.0,
        trailing=0.4, tight_trailing=0.85,
        mr_enabled=True,  mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'xrp': dict(
        path='backtestDatas/xrpusdt_4h.csv', symbol='XRPUSDT',
        slippage_pct=0.0003,
        bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, default_target=10.0,
        trailing=0.5, tight_trailing=0.85,
        mr_enabled=False, mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'link': dict(
        path='backtestDatas/linkusdt_4h.csv', symbol='LINKUSDT',
        slippage_pct=0.0003,
        bb_period=20, bb_std=2.5, rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=20, default_target=7.0,
        trailing=0.5, tight_trailing=0.85,
        mr_enabled=False, mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'avax': dict(
        path='backtestDatas/avaxusdt_4h.csv', symbol='AVAXUSDT',
        slippage_pct=0.0005,
        bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, default_target=10.0,
        trailing=0.4, tight_trailing=0.85,
        mr_enabled=True,  mr_entry_z=1.8, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'arb': dict(
        path='backtestDatas/arbusdt_4h.csv', symbol='ARBUSDT',
        slippage_pct=0.0005,
        bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, default_target=10.0,
        trailing=0.4, tight_trailing=0.65,
        mr_enabled=True,  mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=12, mr_time_mult=2.5,
    ),
    'aave': dict(
        path='backtestDatas/aaveusdt_4h.csv', symbol='AAVEUSDT',
        slippage_pct=0.0005,
        bb_period=20, bb_std=2.0, rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, default_target=10.0,
        trailing=0.4, tight_trailing=0.65,
        mr_enabled=True,  mr_entry_z=2.0, mr_exit_z=0.5,
        mr_max_hl=10, mr_time_mult=2.0,
    ),
}


# ── 데이터 로드 ──────────────────────────────────────────────────
def load_ohlcv(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float).sort_index()


# ── 지표 헬퍼 ────────────────────────────────────────────────────
def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    s = pd.Series(closes)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _macd(closes):
    if len(closes) < 26:
        return None, None
    s = pd.Series(closes)
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    return float(macd.iloc[-1]), float(sig.iloc[-1])


def _atr_val(df_slice, period=14):
    h = df_slice['High']; l = df_slice['Low']; c = df_slice['Close']
    if len(c) < period + 1:
        return float((h - l).iloc[-1])
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def _calc_adx_series(h, l, c, period=14):
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    up = h.diff(); dn = l.shift(1) - l
    pdm = up.where((up > dn) & (up > 0), 0.0)
    mdm = dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / period, adjust=False).mean() / (atr + 1e-9)
    mdi = 100 * mdm.ewm(alpha=1 / period, adjust=False).mean() / (atr + 1e-9)
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def _slope_val(closes, period=20):
    if len(closes) < period:
        return 0.0
    y = closes[-period:].astype(float)
    x = np.arange(period, dtype=float)
    xm, ym = x.mean(), y.mean()
    denom = np.sum((x - xm) ** 2)
    if denom == 0:
        return 0.0
    slope = np.sum((x - xm) * (y - ym)) / denom
    return (slope / ym) * 100 if ym != 0 else 0.0


# ── 진입 시그널 ──────────────────────────────────────────────────
def _trend_signal(df_slice, cfg):
    """BB + MACD + RSI + 볼륨 → ('long'|'short'|None, target_ror)"""
    closes  = df_slice['Close'].values.astype(float)
    volumes = df_slice['Volume'].values.astype(float)

    if len(closes) < max(cfg['bb_period'], 26, VOL_PERIOD) + 2:
        return None, 0.0

    bb_cl  = closes[-cfg['bb_period']:]
    bb_mid = float(np.mean(bb_cl))
    bb_std = float(np.std(bb_cl))
    bb_up  = bb_mid + cfg['bb_std'] * bb_std
    bb_dn  = bb_mid - cfg['bb_std'] * bb_std
    cur    = closes[-1]

    rsi_val = _rsi(closes, cfg.get('rsi_period', 14))
    if rsi_val >= cfg['rsi_overbuy'] or rsi_val <= cfg['rsi_oversell']:
        return None, 0.0

    macd, sig = _macd(closes)
    if macd is None:
        return None, 0.0

    avg_vol = float(np.mean(volumes[-VOL_PERIOD:]))
    cur_vol = volumes[-1]
    if avg_vol <= 0 or cur_vol < avg_vol * VOL_MULT:
        return None, 0.0

    atr        = _atr_val(df_slice)
    target_ror = abs(atr / cur) * 100 if cur > 0 else cfg['default_target']

    if cur > bb_up and macd > sig:
        return 'long',  target_ror
    if cur < bb_dn and macd < sig:
        return 'short', target_ror
    return None, 0.0


def _vb_signal(df_slice):
    """
    VB 시그널 — open + k × prev_range 돌파 시 진입
    반환: ('long'|'short'|None, trigger_price)
    진입가 = 트리거가, 청산은 동일 봉 종가
    """
    if len(df_slice) < 2:
        return None, 0.0

    prev = df_slice.iloc[-2]
    cur  = df_slice.iloc[-1]

    prev_range = float(prev['High'] - prev['Low'])
    prev_close = float(prev['Close'])
    if prev_close <= 0 or prev_range <= 0:
        return None, 0.0
    if prev_range / prev_close * 100 < VB_MIN_RANGE_PCT:
        return None, 0.0

    cur_open  = float(cur['Open'])
    cur_high  = float(cur['High'])
    cur_low   = float(cur['Low'])

    long_trig  = cur_open + VB_K * prev_range
    short_trig = cur_open - VB_K * prev_range

    long_ok  = cur_high >= long_trig  and long_trig  > cur_open
    short_ok = cur_low  <= short_trig and short_trig < cur_open

    if long_ok and short_ok:   # 양방향 동시 터치 → 스킵
        return None, 0.0
    if long_ok:
        return 'long',  long_trig
    if short_ok:
        return 'short', short_trig
    return None, 0.0


def _mr_signal(df_slice, cfg):
    """OU Z-score 기반 → ('long'|'short'|None, target_ror, ou)"""
    # 라이브와 동일하게 최근 300봉만 사용 (전체 히스토리 사용 시 OU 반감기 수백봉으로 폭발)
    closes = df_slice['Close'].values[-300:].astype(float)
    if len(closes) < 30:
        return None, 0.0, None

    ou = fit_ou(closes)
    if ou is None:
        return None, 0.0, None
    if ou['half_life'] > cfg['mr_max_hl']:
        return None, 0.0, None

    z      = ou['zscore']
    target = max(abs(z) * float(ou['sigma_eq']) * 100 * 0.8, 1.5)

    if z <= -cfg['mr_entry_z']:
        return 'long',  target, ou
    if z >= cfg['mr_entry_z']:
        return 'short', target, ou
    return None, 0.0, None


# ── 포지션 관리 ──────────────────────────────────────────────────
def _init_pos(mode, side, entry_price, size, entry_bar, target_ror, atr_ratio, cfg,
              ou=None, feat_vals=None):
    if mode == 'mean_reversion':
        hl   = ou['half_life'] if ou else 6.0
        tmax = hl * cfg['mr_time_mult']
        return {
            'mode': 'mean_reversion', 'side': side,
            'entry_price': entry_price, 'size': size, 'entry_bar': entry_bar,
            'stop_loss': MR_STOP_LOSS, 'target_ror': target_ror,
            'highest_ror': 0.0, 'trailing_active': False, 'phase': 1,
            'atr_ratio': atr_ratio,
            'ou_mu': ou['mu'] if ou else None,
            'ou_sigma_eq': ou['sigma_eq'] if ou else None,
            'mr_time_exit_bars': tmax,
            'feat_vals': feat_vals,
        }
    else:
        if target_ror <= 5:
            target = cfg['default_target']
            stop   = DEFAULT_STOP_LOSS
            atr_r  = 0.05
        else:
            target = target_ror
            stop   = -0.33 * target_ror
            atr_r  = target_ror / 100
        return {
            'mode': 'trend_following', 'side': side,
            'entry_price': entry_price, 'size': size, 'entry_bar': entry_bar,
            'stop_loss': stop, 'target_ror': target,
            'highest_ror': 0.0, 'trailing_active': False, 'phase': 1,
            'atr_ratio': atr_r,
            'feat_vals': feat_vals,
        }


def _calc_ror(pos, price):
    if pos['side'] == 'long':
        return (price / pos['entry_price'] - 1) * 100
    return (pos['entry_price'] / price - 1) * 100


def _stop_price(pos):
    sl    = pos['stop_loss']   # 음수 %
    entry = pos['entry_price']
    return entry * (1 + sl / 100) if pos['side'] == 'long' else entry * (1 - sl / 100)


def _update_trailing(pos, high_ror, cfg):
    """봉 내 최선 ROR(high_ror)로 highest_ror 업데이트 후 trailing 조정"""
    pos['highest_ror'] = max(pos['highest_ror'], high_ror)
    h = pos['highest_ror']

    if h < PHASE2_THRESHOLD:
        pos['phase'] = 1
    elif h < PHASE3_THRESHOLD:
        pos['phase'] = 2
        pos['stop_loss'] = max(pos['stop_loss'], BREAKEVEN_STOP)
    elif h < pos['target_ror']:
        pos['phase'] = 3
        pos['trailing_active'] = True
        pos['stop_loss'] = max(pos['stop_loss'], h * cfg['trailing'])
    else:
        pos['phase'] = 4
        pos['trailing_active'] = True
        pos['stop_loss'] = max(pos['stop_loss'], h * cfg['tight_trailing'])


def _check_exit_trend(pos, bar_high, bar_low, bar_close, bars_held, df_slice, cfg):
    """추세추종 청산. 반환: (exit_price | None, reason)"""
    high_ror = _calc_ror(pos, bar_high if pos['side'] == 'long' else bar_low)
    _update_trailing(pos, high_ror, cfg)

    sp = _stop_price(pos)

    # 1. 스탑 (intrabar)
    if pos['side'] == 'long'  and bar_low  <= sp:
        tag = '트레일링' if pos['trailing_active'] else '손절'
        return sp, f"{tag}({_calc_ror(pos, bar_close):.1f}%)"
    if pos['side'] == 'short' and bar_high >= sp:
        tag = '트레일링' if pos['trailing_active'] else '손절'
        return sp, f"{tag}({_calc_ror(pos, bar_close):.1f}%)"

    # 2. 변동성 급변
    cur_atr_r = _atr_val(df_slice) / bar_close if bar_close > 0 else pos['atr_ratio']
    if pos['atr_ratio'] > 0 and cur_atr_r > pos['atr_ratio'] * VOLATILITY_SPIKE:
        return bar_close, f"변동성급변"

    # 3. 시간 청산
    if bars_held >= TIME_EXIT_BARS_1 and pos['highest_ror'] < TIME_EXIT_ROR_1:
        return bar_close, f"시간초과(24h)"
    if bars_held >= TIME_EXIT_BARS_2 and pos['highest_ror'] < TIME_EXIT_ROR_2:
        return bar_close, f"시간초과(48h)"

    return None, ""


def _check_exit_mr(pos, bar_high, bar_low, bar_close, bars_held, cfg):
    """평균회귀 청산. 반환: (exit_price | None, reason)"""
    close_ror = _calc_ror(pos, bar_close)
    sp        = _stop_price(pos)

    # 1. 손절 (intrabar)
    if pos['side'] == 'long'  and bar_low  <= sp:
        return sp, f"MR손절({close_ror:.1f}%)"
    if pos['side'] == 'short' and bar_high >= sp:
        return sp, f"MR손절({close_ror:.1f}%)"

    # 2. OU Z-score 수렴
    if pos['ou_mu'] is not None and pos['ou_sigma_eq'] and pos['ou_sigma_eq'] > 0:
        if bar_close > 0:
            cur_z = (np.log(bar_close) - pos['ou_mu']) / pos['ou_sigma_eq']
            if abs(cur_z) < cfg['mr_exit_z']:
                return bar_close, f"MR수렴(Z:{cur_z:.2f})"

    # 3. 목표 달성
    if close_ror >= pos['target_ror']:
        return bar_close, f"MR목표({close_ror:.1f}%)"

    # 4. 시간 초과
    if bars_held >= pos['mr_time_exit_bars']:
        return bar_close, f"MR시간({bars_held:.0f}봉)"

    return None, ""


# ── Walk-Forward XGB 헬퍼 ─────────────────────────────────────────
def _wf_retrain(wf_X: list, wf_y: list):
    """Walk-Forward XGB 재학습. 반환: 학습된 XGBClassifier | None"""
    X = np.array(wf_X)           # (n, 13)
    y = np.array(wf_y)
    n = len(y)
    rw = np.array([np.mean(y[max(0, j-20):j]) if j > 0 else 0.5 for j in range(n)])
    X_full = np.hstack([X, rw.reshape(-1, 1)])   # (n, 14)
    mask = ~np.isnan(X_full).any(axis=1)
    if mask.sum() < WF_MIN_TRAIN:
        return None
    m = XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        eval_metric='logloss', random_state=42, verbosity=0,
    )
    m.fit(X_full[mask], y[mask])
    return m


# ── 시뮬레이션 ───────────────────────────────────────────────────
def simulate(df: pd.DataFrame, cfg: dict, use_xgb: bool = False,
             sideways_mode: str = 'mr'):
    """
    단일 코인 시뮬레이션

    use_xgb=False      : ADX + 기울기 기반 레짐 라우팅
    use_xgb=True       : BB 시그널 결과로 Walk-Forward 학습한 XGB 라우팅
                         (학습 전 구간은 ADX 폴백)
    sideways_mode='mr' : 횡보장 → OU 평균회귀 (기존)
    sideways_mode='vb' : 횡보장 → VB 전략 (동일 봉 종가 청산)

    반환: (stats_dict | None, equity_series, trades_list)
    """
    feat_df = build_features(df)
    adx_ser = _calc_adx_series(df['High'], df['Low'], df['Close'])

    slip = cfg.get('slippage_pct', 0.0003)   # 편도 슬리피지

    # Walk-Forward XGB 상태
    wf_X:  list = []
    wf_y:  list = []
    wf_model     = None
    wf_retrain_cnt = 0

    warmup = 300
    cash   = INITIAL
    equity = []
    trades = []
    pos    = None

    for i in range(warmup, len(df)):
        bar_high  = df['High'].iloc[i]
        bar_low   = df['Low'].iloc[i]
        bar_close = df['Close'].iloc[i]
        df_slice  = df.iloc[:i + 1]
        closes    = df_slice['Close'].values.astype(float)

        # ── 청산 체크 ──────────────────────────────────────────────
        if pos is not None:
            bars_held = i - pos['entry_bar']
            if pos['mode'] == 'trend_following':
                exit_p, reason = _check_exit_trend(
                    pos, bar_high, bar_low, bar_close, bars_held, df_slice, cfg)
            else:
                exit_p, reason = _check_exit_mr(
                    pos, bar_high, bar_low, bar_close, bars_held, cfg)

            if exit_p is not None:
                entry = pos['entry_price']
                side  = pos['side']
                sz    = pos['size']
                # 슬리피지: 청산 시 불리한 방향으로 적용
                exit_eff = exit_p * (1 - slip) if side == 'long' else exit_p * (1 + slip)
                pnl   = ((exit_eff - entry) if side == 'long' else (entry - exit_eff)) * sz
                comm  = (entry + exit_eff) * sz * COMMISSION
                pnl  -= comm
                cash += pnl
                trades.append({
                    'dt'    : df.index[i],
                    'dt_in' : df.index[pos['entry_bar']],
                    'mode'  : pos['mode'],
                    'side'  : side,
                    'entry' : entry,
                    'exit_p': exit_p,
                    'pnl'   : pnl,
                    'reason': reason,
                    'bars'  : bars_held,
                })

                # Walk-Forward: 결과 기록 후 재학습 판단
                if use_xgb and pos.get('feat_vals') is not None:
                    wf_X.append(pos['feat_vals'])
                    wf_y.append(1 if pnl > 0 else 0)
                    wf_retrain_cnt += 1
                    if len(wf_y) >= WF_MIN_TRAIN and wf_retrain_cnt >= WF_RETRAIN_EVERY:
                        m = _wf_retrain(wf_X, wf_y)
                        if m is not None:
                            wf_model = m
                        wf_retrain_cnt = 0

                pos = None

        # ── 자산 기록 ──────────────────────────────────────────────
        if pos is not None:
            unreal = ((bar_close - pos['entry_price']) if pos['side'] == 'long'
                      else (pos['entry_price'] - bar_close)) * pos['size']
            equity.append(cash + unreal)
        else:
            equity.append(cash)

        # ── 진입 체크 ──────────────────────────────────────────────
        if pos is not None:
            continue

        feat_row  = feat_df.iloc[i]
        feat_vals = feat_row[list(FEATURE_NAMES[:-1])].values.astype(float)
        if np.isnan(feat_vals).any():
            continue

        adx_val = float(adx_ser.iloc[i])
        slp     = _slope_val(closes)

        # 레짐 라우팅
        if use_xgb and wf_model is not None and len(wf_y) >= WF_MIN_TRAIN:
            # Walk-Forward XGB 라우팅
            rw  = np.mean(wf_y[-20:]) if len(wf_y) >= 20 else 0.5
            row = np.append(feat_vals, rw).reshape(1, -1)
            prob        = float(wf_model.predict_proba(row)[0][1])
            use_trend   = prob >= WF_THRESHOLD
            use_sideways = prob < WF_THRESHOLD
        else:
            # ADX 폴백 (XGB 미사용이거나 학습 전 구간)
            use_trend    = adx_val > cfg['adx_threshold'] and abs(slp) >= MR_SLOPE_THRESHOLD
            use_sideways = not use_trend

        signal, target_ror, mode, ou = None, 0.0, None, None

        if use_trend:
            sig, tr = _trend_signal(df_slice, cfg)
            if sig:
                signal, target_ror, mode = sig, tr, 'trend_following'

        if signal is None and use_sideways:
            if sideways_mode == 'vb':
                # VB: 진입+청산을 같은 봉에서 즉시 처리 (슬리피지 양방향 적용)
                sig, entry_p = _vb_signal(df_slice)
                if sig:
                    if sig == 'long':
                        entry_eff = entry_p * (1 + slip)
                        exit_eff  = bar_close * (1 - slip)
                    else:
                        entry_eff = entry_p * (1 - slip)
                        exit_eff  = bar_close * (1 + slip)
                    sz_vb = cash * POSITION_PCT / entry_eff
                    pnl   = ((exit_eff - entry_eff) if sig == 'long'
                              else (entry_eff - exit_eff)) * sz_vb
                    comm  = (entry_eff + exit_eff) * sz_vb * COMMISSION
                    pnl  -= comm
                    cash += pnl
                    trades.append({
                        'dt':     df.index[i],
                        'dt_in':  df.index[i],
                        'mode':   'vb',
                        'side':   sig,
                        'entry':  entry_eff,
                        'exit_p': exit_eff,
                        'pnl':    pnl,
                        'reason': 'VB종가',
                        'bars':   0,
                    })
                    equity[-1] = cash   # 같은 봉에서 발생한 수익 반영
            elif cfg['mr_enabled']:
                sig, tr, ou_params = _mr_signal(df_slice, cfg)
                if sig:
                    signal, target_ror, mode, ou = sig, tr, 'mean_reversion', ou_params

        if signal is None:
            continue

        # 슬리피지: 진입 시 불리한 방향으로 적용
        entry_eff = bar_close * (1 + slip) if signal == 'long' else bar_close * (1 - slip)
        atr       = _atr_val(df_slice)
        atr_ratio = atr / entry_eff if entry_eff > 0 else 0.03
        size      = cash * POSITION_PCT / entry_eff
        pos = _init_pos(mode, signal, entry_eff, size, i, target_ror, atr_ratio, cfg, ou,
                        feat_vals=feat_vals)

    eq_idx = df.index[warmup: warmup + len(equity)]
    return (_stats(trades, equity, cash),
            pd.Series(equity, index=eq_idx),
            trades)


# ── 통계 ─────────────────────────────────────────────────────────
def _stats(trades: list, equity: list, final_cash: float):
    if not trades:
        return None
    td  = pd.DataFrame(trades)
    eq  = pd.Series(equity)
    tot = len(td)
    won = (td['pnl'] > 0).sum()
    lst = tot - won
    ap  = td.loc[td['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    al  = td.loc[td['pnl'] <= 0, 'pnl'].mean() if lst > 0 else 0
    pl  = abs(ap / al) if al != 0 else 0
    ror = (final_cash - INITIAL) / INITIAL * 100
    rm  = eq.cummax()
    mdd = ((eq - rm) / rm * 100).min()
    ret = eq.pct_change().dropna()
    sh  = ret.mean() / ret.std() * np.sqrt(365 * 6) if ret.std() > 0 else 0
    tr_n = (td['mode'] == 'trend_following').sum()
    mr_n = (td['mode'] == 'mean_reversion').sum()
    vb_n = (td['mode'] == 'vb').sum()
    return dict(total=tot, won=won, lost=lst, win_rate=won/tot*100,
                pl_ratio=pl, ror=ror, sharpe=sh, mdd=mdd,
                avg_win=ap, avg_loss=al, final=final_cash,
                tr_count=int(tr_n), mr_count=int(mr_n), vb_count=int(vb_n),
                trades=td)


# ── 출력 ─────────────────────────────────────────────────────────
def print_detail(coin: str, adx_r, xgb_r):
    print(f"\n{'='*68}")
    print(f"  {coin.upper()}  —  실거래 로직 백테스트 (추세추종+평균회귀)")
    print(f"{'='*68}")
    print(f"  {'':>10}  {'거래':>5}  {'TR':>4}  {'MR':>4}  {'승률':>6}  "
          f"{'ROR':>8}  {'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
    print(f"  {'-'*65}")
    for label, r in [('ADX라우팅', adx_r), ('XGB라우팅', xgb_r)]:
        if r is None:
            print(f"  {label:>10}  결과없음")
            continue
        print(f"  {label:>10}  {r['total']:>5}  {r['tr_count']:>4}  {r['mr_count']:>4}  "
              f"{r['win_rate']:>5.1f}%  {r['ror']:>+7.1f}%  "
              f"{r['sharpe']:>6.2f}  {r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")
    print(f"{'='*68}")

    if adx_r and xgb_r:
        dr = xgb_r['ror'] - adx_r['ror']
        ds = xgb_r['sharpe'] - adx_r['sharpe']
        dm = xgb_r['mdd'] - adx_r['mdd']
        print(f"  XGB vs ADX:  ROR {dr:>+.1f}%  Sharpe {ds:>+.2f}  MDD {dm:>+.1f}%")

    # 연도별 (XGB 기준)
    r = xgb_r or adx_r
    if r:
        label = 'XGB' if xgb_r else 'ADX'
        td = r['trades'].copy()
        td['year'] = td['dt'].dt.year
        print(f"\n  연도별 성과 ({label} 라우팅):")
        print(f"  {'년':>4}  {'거래':>5}  {'TR':>4}  {'MR':>4}  {'승률':>6}  {'ROR':>8}")
        print(f"  {'-'*42}")
        cb = INITIAL
        for yr in sorted(td['year'].unique()):
            g   = td[td['year'] == yr]
            rb  = g['pnl'].sum() / cb * 100
            cb += g['pnl'].sum()
            tr  = (g['mode'] == 'trend_following').sum()
            mr  = (g['mode'] == 'mean_reversion').sum()
            wr  = (g['pnl'] > 0).mean() * 100
            print(f"  {yr:>4}  {len(g):>5}  {tr:>4}  {mr:>4}  {wr:>5.1f}%  {rb:>+7.1f}%")


# ── 차트 ─────────────────────────────────────────────────────────
def plot_results(coin: str, adx_r, xgb_r,
                 eq_adx: pd.Series, eq_xgb: pd.Series,
                 df: pd.DataFrame, save: bool = False):
    import matplotlib
    if save:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.gridspec import GridSpec

    BG    = '#0d1117'; PANEL = '#161b22'; GRID = '#30363d'; TEXT = '#c9d1d9'
    C_ADX = '#8b949e'; C_XGB = '#58a6ff'; WIN  = '#3fb950'; LOSS = '#f85149'

    fig = plt.figure(figsize=(18, 11), facecolor=BG)
    gs  = GridSpec(3, 2, figure=fig,
                   height_ratios=[3, 2, 1.2], width_ratios=[3, 1],
                   hspace=0.08, wspace=0.25)
    ax_price  = fig.add_subplot(gs[0, 0])
    ax_equity = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_dd     = fig.add_subplot(gs[2, 0], sharex=ax_price)
    ax_annual = fig.add_subplot(gs[:, 1])

    for ax in [ax_price, ax_equity, ax_dd, ax_annual]:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.grid(True, color=GRID, linewidth=0.5, alpha=0.6)

    # ── 가격 + 진입 마커 ──────────────────────────────────────────
    ax_price.plot(df.index, df['Close'], color='#30363d', linewidth=0.7, alpha=0.9, zorder=1)
    r = xgb_r or adx_r
    if r:
        td = r['trades']
        for mode, marker, color in [('trend_following', '^', '#58a6ff'),
                                     ('mean_reversion',  's', '#e3b341')]:
            sub = td[td['mode'] == mode]
            wins   = sub[sub['pnl'] > 0]
            losses = sub[sub['pnl'] <= 0]
            ax_price.scatter(wins['dt'],   wins['entry'],
                             marker=marker, color=WIN,  s=16, alpha=0.75, zorder=3)
            ax_price.scatter(losses['dt'], losses['entry'],
                             marker=marker, color=LOSS, s=16, alpha=0.75, zorder=3)

    label = 'XGB' if xgb_r else 'ADX'
    title_r = xgb_r or adx_r
    title = (f"{coin.upper()}  TR+MR({label})  |  "
             f"ROR: {title_r['ror']:+.1f}%  Sharpe: {title_r['sharpe']:.2f}  "
             f"MDD: {title_r['mdd']:.1f}%  WinRate: {title_r['win_rate']:.1f}%"
             if title_r else coin.upper())
    ax_price.set_title(title, color=TEXT, fontsize=10, fontweight='bold', pad=8)
    ax_price.set_ylabel('Price', color=TEXT, fontsize=9)

    # TR/MR 범례 (마커 색 설명)
    from matplotlib.lines import Line2D
    legend_els = [
        Line2D([0], [0], marker='^', color='w', markerfacecolor=WIN,  markersize=7, label='TR Win'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor=LOSS, markersize=7, label='TR Loss'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=WIN,  markersize=7, label='MR Win'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=LOSS, markersize=7, label='MR Loss'),
    ]
    ax_price.legend(handles=legend_els, fontsize=7, facecolor=PANEL,
                    labelcolor=TEXT, loc='upper left')
    plt.setp(ax_price.get_xticklabels(), visible=False)

    # ── 자산 곡선 ─────────────────────────────────────────────────
    ax_equity.plot(eq_adx.index, eq_adx.values, color=C_ADX, linewidth=1.0, alpha=0.7,
                   label=f"ADX  {adx_r['ror']:+.1f}%" if adx_r else "ADX")
    ax_equity.plot(eq_xgb.index, eq_xgb.values, color=C_XGB, linewidth=1.5,
                   label=f"XGB  {xgb_r['ror']:+.1f}%" if xgb_r else "XGB")
    ax_equity.axhline(INITIAL, color=GRID, linewidth=0.8, linestyle='--')
    ax_equity.set_ylabel('Portfolio ($)', color=TEXT, fontsize=9)
    ax_equity.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, loc='upper left')
    plt.setp(ax_equity.get_xticklabels(), visible=False)

    # ── 드로우다운 ────────────────────────────────────────────────
    for eq_s, color, alpha in [(eq_adx, C_ADX, 0.4), (eq_xgb, C_XGB, 0.65)]:
        dd = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
        ax_dd.fill_between(dd.index, dd.values, 0, color=color, alpha=alpha)
    ax_dd.set_ylabel('Drawdown (%)', color=TEXT, fontsize=9)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_dd.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_dd.get_xticklabels(), rotation=30, ha='right', color=TEXT)

    # ── 연도별 수익률 ─────────────────────────────────────────────
    if adx_r and xgb_r:
        td_a = adx_r['trades'].copy(); td_a['year'] = td_a['dt'].dt.year
        td_x = xgb_r['trades'].copy(); td_x['year'] = td_x['dt'].dt.year
        years = sorted(set(td_a['year']) | set(td_x['year']))
        ca, cx = INITIAL, INITIAL
        ra_list, rx_list = [], []
        for yr in years:
            ga = td_a[td_a['year'] == yr]
            gx = td_x[td_x['year'] == yr]
            ra = ga['pnl'].sum() / ca * 100 if len(ga) > 0 else 0.0
            rx = gx['pnl'].sum() / cx * 100 if len(gx) > 0 else 0.0
            ca += ga['pnl'].sum(); cx += gx['pnl'].sum()
            ra_list.append(ra); rx_list.append(rx)

        y  = np.arange(len(years)); bw = 0.35
        ax_annual.barh(y - bw/2, ra_list, bw,
                       color=[WIN if v >= 0 else LOSS for v in ra_list], alpha=0.55, label='ADX')
        ax_annual.barh(y + bw/2, rx_list, bw,
                       color=[WIN if v >= 0 else LOSS for v in rx_list], alpha=0.9,  label='XGB')
        ax_annual.set_yticks(y)
        ax_annual.set_yticklabels([str(yr) for yr in years], color=TEXT, fontsize=9)
        ax_annual.axvline(0, color=GRID, linewidth=1.0)
        ax_annual.set_xlabel('Annual ROR (%)', color=TEXT, fontsize=9)
        ax_annual.set_title('Annual Returns\n(light=ADX, dark=XGB)', color=TEXT, fontsize=9)
        for i, (ra, rx) in enumerate(zip(ra_list, rx_list)):
            ax_annual.text(ra + (1 if ra >= 0 else -1), i - bw/2,
                           f"{ra:+.0f}%", va='center', fontsize=7, color=TEXT, alpha=0.7)
            ax_annual.text(rx + (1 if rx >= 0 else -1), i + bw/2,
                           f"{rx:+.0f}%", va='center', fontsize=7, color=TEXT)

    os.makedirs('charts', exist_ok=True)
    if save:
        out = f"charts/{coin}_live_strategy.png"
        plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
        print(f"  차트 저장: {out}")
        plt.close(fig)
    else:
        plt.show()


# ── main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--coin',       default='all', help='코인 선택 (eth/sol/.../all)')
    parser.add_argument('--plot',       action='store_true', help='차트 표시 (단일 코인)')
    parser.add_argument('--chart-save', action='store_true', help='차트 PNG 저장')
    args = parser.parse_args()

    coins = ({args.coin: COIN_CONFIGS[args.coin]} if args.coin != 'all'
             else COIN_CONFIGS)

    if args.coin != 'all' and args.coin not in COIN_CONFIGS:
        print(f"지원 코인: {', '.join(COIN_CONFIGS.keys())}")
        sys.exit(1)

    summary_rows = []

    for coin, cfg in coins.items():
        path = cfg['path']
        if not os.path.exists(path):
            print(f"  {coin}: 데이터 없음 ({path})"); continue

        print(f"\n[{coin.upper()}] 백테스트 중...")
        df = load_ohlcv(path)
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")

        print(f"  XGB+MR(기존)...", end=' ', flush=True)
        xgb_mr_r, eq_xgb_mr, _ = simulate(df, cfg, use_xgb=True,  sideways_mode='mr')
        print(f"완료 — {xgb_mr_r['total']}거래(TR:{xgb_mr_r['tr_count']}/MR:{xgb_mr_r['mr_count']})  ROR {xgb_mr_r['ror']:+.1f}%"
              if xgb_mr_r else "결과없음")

        print(f"  XGB+VB(신규)...", end=' ', flush=True)
        xgb_vb_r, eq_xgb_vb, _ = simulate(df, cfg, use_xgb=True,  sideways_mode='vb')
        print(f"완료 — {xgb_vb_r['total']}거래(TR:{xgb_vb_r['tr_count']}/VB:{xgb_vb_r['vb_count']})  ROR {xgb_vb_r['ror']:+.1f}%"
              if xgb_vb_r else "결과없음")

        summary_rows.append(dict(
            coin=coin.upper(),
            mr_ror=xgb_mr_r['ror']       if xgb_mr_r else 0,
            vb_ror=xgb_vb_r['ror']       if xgb_vb_r else 0,
            mr_sh=xgb_mr_r['sharpe']     if xgb_mr_r else 0,
            vb_sh=xgb_vb_r['sharpe']     if xgb_vb_r else 0,
            mr_mdd=xgb_mr_r['mdd']       if xgb_mr_r else 0,
            vb_mdd=xgb_vb_r['mdd']       if xgb_vb_r else 0,
            mr_tot=xgb_mr_r['total']     if xgb_mr_r else 0,
            vb_tot=xgb_vb_r['total']     if xgb_vb_r else 0,
            mr_wr=xgb_mr_r['win_rate']   if xgb_mr_r else 0,
            vb_wr=xgb_vb_r['win_rate']   if xgb_vb_r else 0,
            mr_tr=xgb_mr_r['tr_count']   if xgb_mr_r else 0,
            mr_mr=xgb_mr_r['mr_count']   if xgb_mr_r else 0,
            vb_tr=xgb_vb_r['tr_count']   if xgb_vb_r else 0,
            vb_vb=xgb_vb_r['vb_count']   if xgb_vb_r else 0,
        ))

        if args.coin != 'all':
            _print_vb_comparison(coin, xgb_mr_r, xgb_vb_r)
            if args.plot or args.chart_save:
                plot_results(coin, xgb_mr_r, xgb_vb_r, eq_xgb_mr, eq_xgb_vb, df,
                             save=args.chart_save)

    # ── 전체 요약 ─────────────────────────────────────────────────
    if len(summary_rows) > 1 or args.coin == 'all':
        print(f"\n{'='*95}")
        print(f"  XGB 라우팅 — 횡보 전략 비교:  MR(OU 평균회귀)  vs  VB(변동성 돌파)")
        print(f"{'='*95}")
        print(f"  {'코인':<5}  "
              f"{'MR_ROR':>8}  {'VB_ROR':>8}  {'Δ':>7}  "
              f"{'MR_Sh':>6}  {'VB_Sh':>6}  "
              f"{'MR_MDD':>7}  {'VB_MDD':>7}  "
              f"{'MR거래':>6}(TR/MR)  {'VB거래':>6}(TR/VB)  "
              f"{'MR승률':>6}  {'VB승률':>6}")
        print(f"  {'-'*93}")
        for r in summary_rows:
            delta = r['vb_ror'] - r['mr_ror']
            mark  = '▲' if delta > 0 else '▼'
            print(f"  {r['coin']:<5}  "
                  f"{r['mr_ror']:>+7.1f}%  {r['vb_ror']:>+7.1f}%  "
                  f"{mark}{abs(delta):>5.1f}%  "
                  f"{r['mr_sh']:>6.2f}  {r['vb_sh']:>6.2f}  "
                  f"{r['mr_mdd']:>6.1f}%  {r['vb_mdd']:>6.1f}%  "
                  f"{r['mr_tot']:>6}({r['mr_tr']}/{r['mr_mr']})  "
                  f"{r['vb_tot']:>6}({r['vb_tr']}/{r['vb_vb']})  "
                  f"{r['mr_wr']:>5.1f}%  {r['vb_wr']:>5.1f}%")
        print(f"{'='*95}")

        improved  = sum(1 for r in summary_rows if r['vb_ror'] > r['mr_ror'])
        avg_delta = np.mean([r['vb_ror'] - r['mr_ror'] for r in summary_rows])
        print(f"\n  VB > MR: {improved}/{len(summary_rows)}코인  |  평균 Δ ROR: {avg_delta:+.1f}%")


def _print_vb_comparison(coin: str, mr_r, vb_r):
    """단일 코인 MR vs VB 상세 비교"""
    print(f"\n{'='*68}")
    print(f"  {coin.upper()}  —  횡보 전략 비교 (XGB 라우팅 기준)")
    print(f"{'='*68}")
    print(f"  {'':>10}  {'거래':>5}  {'TR':>4}  {'MR/VB':>5}  {'승률':>6}  "
          f"{'ROR':>8}  {'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
    print(f"  {'-'*65}")
    for label, r, sub_key in [('XGB+MR', mr_r, 'mr_count'), ('XGB+VB', vb_r, 'vb_count')]:
        if r is None:
            print(f"  {label:>10}  결과없음"); continue
        sub_n = r.get(sub_key, 0)
        print(f"  {label:>10}  {r['total']:>5}  {r['tr_count']:>4}  {sub_n:>5}  "
              f"{r['win_rate']:>5.1f}%  {r['ror']:>+7.1f}%  "
              f"{r['sharpe']:>6.2f}  {r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")
    print(f"{'='*68}")

    if mr_r and vb_r:
        dr = vb_r['ror']    - mr_r['ror']
        ds = vb_r['sharpe'] - mr_r['sharpe']
        dm = vb_r['mdd']    - mr_r['mdd']
        print(f"  VB vs MR:  ROR {dr:>+.1f}%  Sharpe {ds:>+.2f}  MDD {dm:>+.1f}%")

    # 연도별 (VB 기준)
    r = vb_r or mr_r
    if r:
        label = 'VB' if vb_r else 'MR'
        td = r['trades'].copy()
        td['year'] = td['dt'].dt.year
        print(f"\n  연도별 성과 (XGB+{label}):")
        print(f"  {'년':>4}  {'거래':>5}  {'TR':>4}  {'VB/MR':>5}  {'승률':>6}  {'ROR':>8}")
        print(f"  {'-'*44}")
        cb = INITIAL
        for yr in sorted(td['year'].unique()):
            g   = td[td['year'] == yr]
            rb  = g['pnl'].sum() / cb * 100
            cb += g['pnl'].sum()
            tr  = (g['mode'] == 'trend_following').sum()
            sw  = ((g['mode'] == 'vb') | (g['mode'] == 'mean_reversion')).sum()
            wr  = (g['pnl'] > 0).mean() * 100
            print(f"  {yr:>4}  {len(g):>5}  {tr:>4}  {sw:>5}  {wr:>5.1f}%  {rb:>+7.1f}%")
