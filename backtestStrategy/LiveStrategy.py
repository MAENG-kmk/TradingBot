"""
LiveStrategy — base_strategy.py 실거래 로직을 backtrader로 동일하게 구현

진입:
  시장 국면 판단 (ADX + 회귀기울기)
  ├─ 추세장: BB 돌파 + MACD 확인 + RSI 필터 + 볼륨 필터
  └─ 횡보장: OU Z-score 기반 평균회귀 (반감기 필터 포함)

청산:
  추세추종: 4단계 트레일링 + 시간청산 + 변동성급변
  평균회귀: OU Z-score 수렴 or 목표도달 or 손절 or 반감기×2.5배 시간청산
"""
import math
import numpy as np
import backtrader as bt
import sys, os
sys.path.append(os.path.abspath('.'))
from tools.ouProcess import fit_ou


# ──────────────────────────────────────────────
#  회귀기울기 (trendFilter.py 동일 로직)
# ──────────────────────────────────────────────
def regression_slope(closes_arr, period=20):
    if len(closes_arr) < period:
        return 0.0
    y = closes_arr[-period:].astype(float)
    x = np.arange(period, dtype=float)
    x_mean, y_mean = x.mean(), y.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return 0.0
    slope = np.sum((x - x_mean) * (y - y_mean)) / denom
    return (slope / y_mean) * 100 if y_mean != 0 else 0.0


class LiveStrategy(bt.Strategy):
    """
    base_strategy.py 실거래 로직 충실 재현
    4H 봉 기준 (6봉=24h, 3봉=12h, 12봉=48h)
    """
    params = dict(
        # ── 시장 국면 판단 ──
        adx_period=14,
        adx_threshold=20,
        slope_period=20,
        slope_threshold=0.05,

        # ── 볼륨 필터 ──
        vol_period=20,          # 볼륨 평균 계산 기간
        vol_mult=2.0,           # 현재 볼륨 > 평균 × 배수일 때만 진입

        # ── 추세추종 진입 ──
        tr_bb_period=20,
        tr_bb_std=2.0,
        rsi_period=14,
        rsi_overbuy=80,
        rsi_oversell=20,

        # ── 평균회귀 진입 (OU 기반) ──
        mr_enabled=True,        # False면 평균회귀 완전 비활성화
        mr_ou_entry_z=2.0,      # 진입 Z-score 임계값
        mr_ou_exit_z=0.5,       # 청산 Z-score 임계값 (평균 수렴 완료)
        mr_max_halflife=12,     # 최대 허용 반감기 (봉, 12봉=48h)
        mr_stop_loss=-1.5,
        mr_time_halflife_mult=2.5,  # 시간청산 = 반감기 × 배수

        # ── 추세추종 청산 (4단계 트레일링) ──
        default_target_ror=10.0,
        default_stop_loss=-2.5,
        phase2_threshold=3.0,
        phase3_threshold=6.0,
        breakeven_stop=0.5,
        trailing_ratio=0.6,
        tight_trailing_ratio=0.75,

        # ── 시간 청산 ──
        time_exit_bars1=6,      # 24h
        time_exit_ror1=1.0,
        time_exit_bars2=12,     # 48h
        time_exit_ror2=2.0,

        # ── 변동성 급변 ──
        volatility_spike=3.0,

        # ── 포지션 크기 ──
        risk_percent=0.99,      # 자본의 99% 투입 (실거래: 자본/10 × 0.99)
    )

    def __init__(self):
        self.atr  = bt.ind.ATR(self.data, period=14)
        self.dmi  = bt.ind.DirectionalMovementIndex(self.data, period=self.p.adx_period)
        self.macd = bt.ind.MACD(self.data.close)  # 기본값: 12, 26, 9
        self.rsi  = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.vol_ma = bt.ind.SMA(self.data.volume, period=self.p.vol_period)
        self._reset()

    def _reset(self):
        self.entry_price     = 0.0
        self.entry_atr_ratio = 0.0
        self.stop_loss_ror   = 0.0
        self.target_ror      = 0.0
        self.highest_ror     = 0.0
        self.bars_in_trade   = 0
        self.phase           = 1
        self.trailing_active = False
        self.mode            = None   # 'trend_following' | 'mean_reversion'
        # OU 상태 (평균회귀용)
        self.ou_mu           = None
        self.ou_sigma_eq     = None
        self.ou_half_life    = None
        self.mr_time_bars    = 999

    # ──────────────────────────────────────────
    #  시장 국면 판단 (checkMarketRegime)
    # ──────────────────────────────────────────
    def _market_regime(self):
        closes = np.array(self.data.close.get(size=60), dtype=float)
        if len(closes) < 50:
            return 'ranging'

        adx = self.dmi.adx[0]
        slope = regression_slope(closes, self.p.slope_period)

        # ADX 추세 판단 (checkTrendStrength)
        is_trending = adx >= self.p.adx_threshold
        if not is_trending and adx > 15:
            # ADX 연속 상승 중 (breakout 감지)
            adx1 = self.dmi.adx[-1]
            adx2 = self.dmi.adx[-2]
            if adx > adx1 > adx2:
                is_trending = True

        if is_trending and slope > self.p.slope_threshold:
            return 'uptrend'
        elif is_trending and slope < -self.p.slope_threshold:
            return 'downtrend'
        else:
            return 'ranging'

    # ──────────────────────────────────────────
    #  볼린저밴드
    # ──────────────────────────────────────────
    def _bb(self, period, std_mult):
        closes = np.array(self.data.close.get(size=period), dtype=float)
        if len(closes) < period:
            return None, None, None
        mid   = closes.mean()
        sigma = closes.std()
        return mid + std_mult * sigma, mid, mid - std_mult * sigma

    # ──────────────────────────────────────────
    #  볼륨 필터
    # ──────────────────────────────────────────
    def _volume_ok(self):
        """현재 볼륨이 평균 대비 vol_mult배 이상인지 확인"""
        avg_vol = self.vol_ma[0]
        if avg_vol <= 0:
            return False
        return self.data.volume[0] >= avg_vol * self.p.vol_mult

    # ──────────────────────────────────────────
    #  진입 신호
    # ──────────────────────────────────────────
    def _trend_following_signal(self):
        upper, mid, lower = self._bb(self.p.tr_bb_period, self.p.tr_bb_std)
        if upper is None:
            return None

        price  = self.data.close[0]
        rsi    = self.rsi[0]
        macd_v = self.macd.lines.macd[0]
        sig_v  = self.macd.lines.signal[0]

        # RSI 극단이면 진입 금지
        if rsi >= self.p.rsi_overbuy or rsi <= self.p.rsi_oversell:
            return None

        # BB 돌파 + MACD + 볼륨 확인
        if price > upper and macd_v > sig_v and self._volume_ok():
            return 'long'
        if price < lower and macd_v < sig_v and self._volume_ok():
            return 'short'
        return None

    def _mean_reversion_signal(self):
        """OU 프로세스 기반 평균회귀 신호"""
        closes = np.array(self.data.close.get(size=100), dtype=float)
        if len(closes) < 30:
            return None, None

        ou = fit_ou(closes)
        if ou is None:
            return None, None

        # 반감기 필터 — 회귀가 너무 느리면 스킵
        if ou['half_life'] > self.p.mr_max_halflife:
            return None, None

        z = ou['zscore']
        target_ror = abs(z) * float(ou['sigma_eq']) * 100 * 0.8

        if z <= -self.p.mr_ou_entry_z:
            return 'long', ou
        if z >= self.p.mr_ou_entry_z:
            return 'short', ou
        return None, None

    # ──────────────────────────────────────────
    #  포지션 진입
    # ──────────────────────────────────────────
    def _enter(self, direction, mode, ou=None):
        price = self.data.close[0]
        cash  = self.broker.get_cash()
        size  = (cash * self.p.risk_percent) / price
        if size <= 0:
            return

        if direction == 'long':
            self.buy(size=size)
        else:
            self.sell(size=size)

        self._reset()
        self.entry_price = price
        self.mode        = mode

        atr_v = self.atr[0]
        self.entry_atr_ratio = atr_v / price if price > 0 else 0.0

        if mode == 'mean_reversion' and ou is not None:
            z = ou['zscore']
            self.target_ror    = max(abs(z) * float(ou['sigma_eq']) * 100 * 0.8, 1.5)
            self.stop_loss_ror = self.p.mr_stop_loss
            self.ou_mu         = ou['mu']
            self.ou_sigma_eq   = ou['sigma_eq']
            self.ou_half_life  = ou['half_life']
            self.mr_time_bars  = int(ou['half_life'] * self.p.mr_time_halflife_mult) + 1
        else:
            # ATR 기반 동적 목표
            target = abs(atr_v / price) * 100
            if target <= 5:
                target = self.p.default_target_ror
                stop   = self.p.default_stop_loss
            else:
                stop = -0.33 * target  # 3:1 손익비
            self.target_ror    = target
            self.stop_loss_ror = stop

    # ──────────────────────────────────────────
    #  현재 ROR 계산
    # ──────────────────────────────────────────
    def _ror(self):
        if self.entry_price == 0:
            return 0.0
        price = self.data.close[0]
        if self.position.size > 0:
            return (price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - price) / self.entry_price * 100

    # ──────────────────────────────────────────
    #  4단계 트레일링 (_update_trailing)
    # ──────────────────────────────────────────
    def _update_trailing(self, ror):
        if ror > self.highest_ror:
            self.highest_ror = ror
        h = self.highest_ror

        if h < self.p.phase2_threshold:
            self.phase = 1
        elif h < self.p.phase3_threshold:
            self.phase = 2
            self.stop_loss_ror = max(self.stop_loss_ror, self.p.breakeven_stop)
        elif h < self.target_ror:
            self.phase = 3
            self.trailing_active = True
            self.stop_loss_ror = max(self.stop_loss_ror, h * self.p.trailing_ratio)
        else:
            self.phase = 4
            self.trailing_active = True
            self.stop_loss_ror = max(self.stop_loss_ror, h * self.p.tight_trailing_ratio)

    # ──────────────────────────────────────────
    #  청산 조건 체크
    # ──────────────────────────────────────────
    def _check_time(self):
        b = self.bars_in_trade
        h = self.highest_ror
        if b > self.p.time_exit_bars1 and h < self.p.time_exit_ror1:
            return True
        if b > self.p.time_exit_bars2 and h < self.p.time_exit_ror2:
            return True
        return False

    def _check_volatility(self):
        if self.entry_atr_ratio <= 0:
            return False
        cur_ratio = self.atr[0] / self.data.close[0]
        return cur_ratio > self.entry_atr_ratio * self.p.volatility_spike

    # ──────────────────────────────────────────
    #  메인 루프
    # ──────────────────────────────────────────
    def next(self):
        if not self.position:
            regime = self._market_regime()

            if regime in ('uptrend', 'downtrend'):
                sig = self._trend_following_signal()
                if sig:
                    self._enter(sig, 'trend_following')
            elif self.p.mr_enabled:
                sig, ou = self._mean_reversion_signal()
                if sig:
                    self._enter(sig, 'mean_reversion', ou=ou)
        else:
            self.bars_in_trade += 1
            ror = self._ror()

            # ── 평균회귀 청산 ──
            if self.mode == 'mean_reversion':
                # 1. OU Z-score 수렴 청산
                if self.ou_mu is not None and self.ou_sigma_eq:
                    try:
                        cur_z = (math.log(self.data.close[0]) - self.ou_mu) / self.ou_sigma_eq
                        if abs(cur_z) < self.p.mr_ou_exit_z:
                            self.close(); self._reset(); return
                    except Exception:
                        pass
                # 2. 목표 수익
                if ror >= self.target_ror:
                    self.close(); self._reset(); return
                # 3. 손절
                if ror <= self.stop_loss_ror:
                    self.close(); self._reset(); return
                # 4. 반감기 기반 시간청산
                if self.bars_in_trade > self.mr_time_bars:
                    self.close(); self._reset()
                return

            # ── 추세추종 청산 ──
            self._update_trailing(ror)

            if ror < self.stop_loss_ror:
                self.close(); self._reset(); return
            if self._check_volatility():
                self.close(); self._reset(); return
            if self._check_time():
                self.close(); self._reset(); return
