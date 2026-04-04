"""
XGBoost 레짐 필터 — 라이브 트레이딩 통합용

사용법 (strategy.py):
  from tools.regime_filter import RegimeFilter

  # 전략 __init__ 또는 모듈 레벨에서 모델 로드
  _regime = RegimeFilter.load('models/regime_DOGEUSDT.pkl')

  # check_entry_signal() 내부에서
  prob = _regime.predict(df)   # df: get_data(limit=300) 결과
  if prob < 0.55:
      return None, 0, None, None
"""

import os
import numpy as np
import pandas as pd
import joblib
from xgboost import XGBClassifier


FEATURE_NAMES = [
    'atr_ratio',       # ATR / 가격 (정규화 변동성)
    'atr_pct',         # ATR 롤링 252봉 분위수 (0~100)
    'adx',             # 추세 강도
    'rsi14',           # RSI(14)
    'bb_width',        # BB 폭 / mid (정규화)
    'ma20_slope',      # MA20 기울기 (5봉)
    'price_vs_ma20',   # 가격 / MA20 - 1 (%)
    'price_vs_ma50',   # 가격 / MA50 - 1 (%)
    'vol_ratio',       # 거래량 / MA20 거래량
    'range_pct',       # 직전봉 range / close (%)
    'mom5',            # 5봉 모멘텀 (%)
    'hour',            # 캔들 시작 시(0~23)
    'dow',             # 요일 (0=월 ~ 6=일)
    'recent_wr',       # 최근 20 시그널 승률
]


# ── 지표 계산 ────────────────────────────────────────────────────

def _calc_adx(h, l, c, period=14):
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    up   = h - h.shift(1)
    down = l.shift(1) - l
    plus_dm  = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)

    plus_di  = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / (atr + 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / (atr + 1e-9)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx


def _calc_atr(h, l, c, period=14):
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _rolling_percentile(series, window=252):
    """각 시점에서 과거 window봉 내 분위수 (0~100)"""
    vals   = series.values.astype(float)
    result = np.full(len(vals), np.nan)
    for i in range(window - 1, len(vals)):
        w = vals[i - window + 1: i + 1]
        if not np.isnan(w).any():
            result[i] = (w <= w[-1]).mean() * 100
    return pd.Series(result, index=series.index)


def build_features(df) -> pd.DataFrame:
    """
    OHLCV DataFrame → 피처 DataFrame
    df는 최소 300봉 이상 권장 (warmup 포함)
    """
    o = df['Open']; h = df['High']; l = df['Low']
    c = df['Close']; v = df['Volume']

    # ATR
    atr14      = _calc_atr(h, l, c, 14)
    atr_ratio  = atr14 / (c + 1e-9)
    atr_pct    = _rolling_percentile(atr14, 252)

    # ADX
    adx = _calc_adx(h, l, c, 14)

    # RSI(14)
    delta = c.diff()
    up    = delta.clip(lower=0)
    dn    = (-delta).clip(lower=0)
    rs    = up.ewm(alpha=1/14, adjust=False).mean() / (dn.ewm(alpha=1/14, adjust=False).mean() + 1e-9)
    rsi14 = 100 - 100 / (1 + rs)

    # Bollinger Band 폭
    ma20    = c.rolling(20).mean()
    std20   = c.rolling(20).std()
    bb_width = 2 * std20 / (ma20 + 1e-9)

    # MA 기울기 & 위치
    ma50         = c.rolling(50).mean()
    ma20_slope   = ma20.diff(5) / (ma20.shift(5) + 1e-9) * 100
    price_vs_ma20 = (c / (ma20 + 1e-9) - 1) * 100
    price_vs_ma50 = (c / (ma50 + 1e-9) - 1) * 100

    # 거래량 비율
    vol_ratio = v / (v.rolling(20).mean() + 1e-9)

    # 직전봉 range %
    prev_range = (h - l).shift(1)
    prev_close = c.shift(1)
    range_pct  = prev_range / (prev_close + 1e-9) * 100

    # 5봉 모멘텀
    mom5 = (c / (c.shift(5) + 1e-9) - 1) * 100

    # 시간 피처
    hour = pd.Series(df.index.hour,       index=df.index, dtype=float)
    dow  = pd.Series(df.index.dayofweek,  index=df.index, dtype=float)

    feat = pd.DataFrame({
        'atr_ratio'   : atr_ratio,
        'atr_pct'     : atr_pct,
        'adx'         : adx,
        'rsi14'       : rsi14,
        'bb_width'    : bb_width,
        'ma20_slope'  : ma20_slope,
        'price_vs_ma20': price_vs_ma20,
        'price_vs_ma50': price_vs_ma50,
        'vol_ratio'   : vol_ratio,
        'range_pct'   : range_pct,
        'mom5'        : mom5,
        'hour'        : hour,
        'dow'         : dow,
    }, index=df.index)

    return feat


# ── RegimeFilter 클래스 ──────────────────────────────────────────

class RegimeFilter:
    """
    XGBoost 기반 레짐 필터

    학습:
      rf = RegimeFilter()
      rf.fit(X, y)           # X: (n, 14) ndarray, y: (n,) 0/1

    라이브 예측:
      rf = RegimeFilter.load('models/regime_DOGEUSDT.pkl')
      prob = rf.predict(df)  # df: get_data() 결과 DataFrame
      # prob: float 0~1, 높을수록 진입 유리
    """

    DEFAULT_PARAMS = dict(
        n_estimators    = 200,
        max_depth       = 3,
        learning_rate   = 0.05,
        subsample       = 0.8,
        colsample_bytree= 0.8,
        min_child_weight= 5,
        eval_metric     = 'logloss',
        random_state    = 42,
        verbosity       = 0,
    )

    def __init__(self, params: dict = None):
        p = {**self.DEFAULT_PARAMS, **(params or {})}
        self.model = XGBClassifier(**p)
        self._recent_labels: list = []   # 최근 시그널 승패 (live용)
        self._fitted = False

    # ── 학습 ────────────────────────────────────────────────────

    def fit(self, X: np.ndarray, y: np.ndarray):
        """
        X: (n_samples, 13) 피처 (recent_wr 제외)
        y: (n_samples,) 0 or 1
        recent_wr 컬럼은 fit 시 0.5로 채워 내부에서 추가
        """
        recent_wr_col = np.full((len(X), 1), 0.5)
        X_full = np.hstack([X, recent_wr_col])
        mask = ~np.isnan(X_full).any(axis=1)
        self.model.fit(X_full[mask], y[mask])
        self._fitted = True

    def fit_with_history(self, X: np.ndarray, y: np.ndarray):
        """
        recent_wr를 실제 히스토리로 계산해서 학습
        (walk-forward 내부 사용)
        """
        n = len(X)
        recent_wr = np.zeros(n)
        for i in range(n):
            if i >= 20:
                recent_wr[i] = np.mean(y[i-20:i])
            else:
                recent_wr[i] = 0.5
        X_full = np.hstack([X, recent_wr.reshape(-1, 1)])
        mask = ~np.isnan(X_full).any(axis=1)
        self.model.fit(X_full[mask], y[mask])
        self._fitted = True

    # ── 예측 (라이브) ────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> float:
        """
        df: 최근 300봉 이상의 OHLCV DataFrame (get_data 결과)
        반환: float 0~1 (1에 가까울수록 진입 유리)
        """
        if not self._fitted:
            return 0.5

        feat = build_features(df)
        last = feat.iloc[-1][list(FEATURE_NAMES[:-1])].values.astype(float)

        recent_wr = np.mean(self._recent_labels[-20:]) if len(self._recent_labels) >= 20 else 0.5
        row = np.append(last, recent_wr).reshape(1, -1)

        if np.isnan(row).any():
            return 0.5

        return float(self.model.predict_proba(row)[0][1])

    def record_outcome(self, profit: float):
        """진입 후 결과를 기록 (라이브 recent_wr 업데이트)"""
        self._recent_labels.append(1 if profit > 0 else 0)
        if len(self._recent_labels) > 100:
            self._recent_labels = self._recent_labels[-100:]

    # ── 피처 중요도 ──────────────────────────────────────────────

    @property
    def feature_importances(self) -> dict:
        if not self._fitted:
            return {}
        return dict(zip(FEATURE_NAMES, self.model.feature_importances_))

    # ── 저장 / 로드 ──────────────────────────────────────────────

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        joblib.dump(self, path)
        print(f"  모델 저장: {path}")

    @classmethod
    def load(cls, path: str) -> 'RegimeFilter':
        if not os.path.exists(path):
            raise FileNotFoundError(f"모델 파일 없음: {path}\n"
                                    f"  → python backtest_xgb_regime.py 를 먼저 실행하세요.")
        obj = joblib.load(path)
        return obj
