import backtrader as bt
import numpy as np


class CoinBacktestStrategy(bt.Strategy):
    """
    코인별 백테스트 공통 전략

    진입: 추세장 → EMA + RSI + MACD + ADX
          횡보장 → 볼린저밴드 + RSI 평균회귀
    청산: 추세추종 → 4단계 트레일링 (재진입 방지 포함)
          평균회귀 → 목표/손절/시간 단순 청산
    """
    params = dict(
        # 진입 (추세추종 — 볼린저밴드 돌파)
        tr_bb_period=20,
        tr_bb_std=2.0,
        rsi_period=14,
        rsi_overbuy=80,
        rsi_oversell=20,
        atr_period=14,
        atr_multiplier=2.2,
        risk_percent=0.02,
        adx_period=14,
        adx_threshold=20,
        # 청산: 4단계 트레일링
        target_ror_pct=7.0,
        phase2_threshold=3.0,
        phase3_threshold=5.0,
        breakeven_stop=0.5,
        trailing_ratio=0.6,
        tight_trailing_ratio=0.75,
        time_exit_bars1=6,
        time_exit_ror1=1.0,
        time_exit_bars2=12,
        time_exit_ror2=2.0,
        volatility_spike=3.0,
        # 평균회귀 파라미터
        mr_enabled=True,
        mr_bb_period=20,
        mr_bb_std=2.0,
        mr_rsi_overbuy=70,
        mr_rsi_oversell=30,
        mr_target_ror=2.5,
        mr_stop_loss=-2.0,
        mr_time_exit_bars=3,    # 12h = 3 × 4h봉
        # 회귀 기울기
        slope_period=20,
        slope_threshold=0.05,
    )

    def __init__(self):
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.macd = bt.ind.MACD(self.data.close)
        self.dmi = bt.ind.DirectionalMovementIndex(self.data, period=self.p.adx_period)
        self._reset()

    def _reset(self):
        self.entry_price = 0
        self.entry_atr = 0
        self.stop_loss_ror = 0
        self.highest_ror = 0
        self.bars_in_trade = 0
        self.phase = 1
        self.trailing_active = False
        self.trade_mode = 'trend_following'

    def _calc_ror(self):
        if self.entry_price == 0:
            return 0
        if self.position.size > 0:
            return (self.data.close[0] - self.entry_price) / self.entry_price * 100
        return (self.entry_price - self.data.close[0]) / self.entry_price * 100

    def _update_trailing_stop(self, ror):
        if ror > self.highest_ror:
            self.highest_ror = ror
        highest = self.highest_ror

        if highest < self.p.phase2_threshold:
            self.phase = 1
            return
        if highest < self.p.phase3_threshold:
            self.phase = 2
            self.stop_loss_ror = max(self.stop_loss_ror, self.p.breakeven_stop)
            return
        if highest < self.p.target_ror_pct:
            self.phase = 3
            self.trailing_active = True
            self.stop_loss_ror = max(self.stop_loss_ror, highest * self.p.trailing_ratio)
            return
        self.phase = 4
        self.trailing_active = True
        self.stop_loss_ror = max(self.stop_loss_ror, highest * self.p.tight_trailing_ratio)

    def _check_time_exit(self):
        if self.bars_in_trade > self.p.time_exit_bars1 and self.highest_ror < self.p.time_exit_ror1:
            return True
        if self.bars_in_trade > self.p.time_exit_bars2 and self.highest_ror < self.p.time_exit_ror2:
            return True
        return False

    def _check_volatility_exit(self):
        if self.entry_atr > 0 and self.atr[0] > self.entry_atr * self.p.volatility_spike:
            return True
        return False

    def _check_trend_strength(self):
        adx = self.dmi.adx[0]
        if adx >= self.p.adx_threshold:
            return True
        if adx > 15 and self.dmi.adx[0] > self.dmi.adx[-1] > self.dmi.adx[-2]:
            return True
        return False

    def _calc_regression_slope(self):
        """최근 N봉의 종가 선형회귀 기울기 (% 정규화)"""
        period = self.p.slope_period
        if len(self.data) < period:
            return 0.0
        y = np.array([self.data.close[-i] for i in range(period - 1, -1, -1)], dtype=float)
        x = np.arange(period, dtype=float)
        x_mean = x.mean()
        y_mean = y.mean()
        slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
        if y_mean == 0:
            return 0.0
        return (slope / y_mean) * 100

    def _get_market_regime(self):
        """시장 상태 판단: uptrend / downtrend / ranging"""
        is_trending = self._check_trend_strength()
        slope = self._calc_regression_slope()

        if is_trending and slope > self.p.slope_threshold:
            return 'uptrend'
        elif is_trending and slope < -self.p.slope_threshold:
            return 'downtrend'
        return 'ranging'

    def _check_trend_entry(self):
        """추세추종 진입 — 볼린저밴드 돌파 + MACD 확인"""
        period = self.p.tr_bb_period
        if len(self.data) < period:
            return None

        closes = np.array([self.data.close[-i] for i in range(period - 1, -1, -1)], dtype=float)
        bb_mid = closes.mean()
        bb_std = closes.std()
        bb_upper = bb_mid + self.p.tr_bb_std * bb_std
        bb_lower = bb_mid - self.p.tr_bb_std * bb_std

        price = self.data.close[0]
        rsi = self.rsi[0]

        if rsi >= self.p.rsi_overbuy or rsi <= self.p.rsi_oversell:
            return None

        if price > bb_upper and self.macd.lines.macd[0] > self.macd.lines.signal[0]:
            return 'long'
        if price < bb_lower and self.macd.lines.macd[0] < self.macd.lines.signal[0]:
            return 'short'
        return None

    def _check_mr_entry(self):
        """평균회귀 진입 시그널 확인 → 'long'/'short'/None"""
        period = self.p.mr_bb_period
        if len(self.data) < period:
            return None

        closes = np.array([self.data.close[-i] for i in range(period - 1, -1, -1)], dtype=float)
        bb_mid = closes.mean()
        bb_std = closes.std()
        bb_upper = bb_mid + self.p.mr_bb_std * bb_std
        bb_lower = bb_mid - self.p.mr_bb_std * bb_std

        price = self.data.close[0]
        rsi = self.rsi[0]

        if price <= bb_lower and rsi <= self.p.mr_rsi_oversell:
            return 'long'
        if price >= bb_upper and rsi >= self.p.mr_rsi_overbuy:
            return 'short'
        return None

    def _should_hold(self):
        """재진입 방지: 같은 방향 시그널이 있으면 True"""
        current_side = 'long' if self.position.size > 0 else 'short'
        regime = self._get_market_regime()

        if regime in ('uptrend', 'downtrend'):
            signal = self._check_trend_entry()
        else:
            signal = self._check_mr_entry()

        return signal is not None and signal == current_side

    def _enter(self, direction, mode='trend_following'):
        atr_val = self.atr[0]
        risk_per_unit = atr_val * self.p.atr_multiplier
        if risk_per_unit <= 0:
            return

        init_stop_ror = -(atr_val * self.p.atr_multiplier) / self.data.close[0] * 100
        size = (self.broker.get_cash() * self.p.risk_percent) / risk_per_unit
        if size <= 0:
            return

        if direction == 'long':
            self.buy(size=size)
        else:
            self.sell(size=size)

        self._reset()
        self.entry_price = self.data.close[0]
        self.entry_atr = atr_val
        self.trade_mode = mode

        if mode == 'mean_reversion':
            self.stop_loss_ror = self.p.mr_stop_loss
        else:
            self.stop_loss_ror = init_stop_ror

    def next(self):
        if not self.position:
            regime = self._get_market_regime()

            if regime in ('uptrend', 'downtrend'):
                signal = self._check_trend_entry()
                if signal:
                    self._enter(signal, 'trend_following')
            elif self.p.mr_enabled:
                signal = self._check_mr_entry()
                if signal:
                    self._enter(signal, 'mean_reversion')
        else:
            self.bars_in_trade += 1
            ror = self._calc_ror()

            # === 평균회귀 모드 청산 ===
            if self.trade_mode == 'mean_reversion':
                if ror >= self.p.mr_target_ror:
                    self.close()
                    self._reset()
                elif ror <= self.p.mr_stop_loss:
                    self.close()
                    self._reset()
                elif self.bars_in_trade > self.p.mr_time_exit_bars:
                    self.close()
                    self._reset()
                return

            # === 추세추종 모드 청산 ===
            self._update_trailing_stop(ror)

            should_close = False
            is_hard_stop = False

            if ror < self.stop_loss_ror:
                should_close = True
                if not self.trailing_active:
                    is_hard_stop = True

            if not should_close and self._check_volatility_exit():
                should_close = True
            if not should_close and self._check_time_exit():
                should_close = True

            if should_close:
                # 재진입 방지: 하드스탑 외에는 같은 방향 시그널 시 홀드
                if not is_hard_stop and self._should_hold():
                    return
                self.close()
                self._reset()
