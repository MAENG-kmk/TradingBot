import backtrader as bt
import numpy as np
import pandas as pd


class CoinBacktestStrategy(bt.Strategy):
    """
    코인별 백테스트 공통 전략

    진입: 추세장 → EMA + RSI + MACD + ADX
          횡보장 → 볼린저밴드 + RSI 평균회귀
    청산: 추세추종 → 4단계 트레일링 (재진입 방지 포함)
          평균회귀 → 목표/손절/시간 단순 청산

    정밀 백테스트:
      - 손절·목표 체크를 종가가 아닌 캔들 고가/저가 기준으로 수행
      - 4h 캔들 내 고가/저가가 동시에 손절·목표를 터치할 때
        1h 데이터(intrabar_data)로 선후를 판별
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
        # 정밀 백테스트용 1h 데이터 (pandas DataFrame, Date 인덱스)
        intrabar_data=None,
    )

    def __init__(self):
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.macd = bt.ind.MACD(self.data.close)
        self.dmi = bt.ind.DirectionalMovementIndex(self.data, period=self.p.adx_period)
        self._pending_entry = None
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

    def _calc_ror(self, price=None):
        if self.entry_price == 0:
            return 0
        p = price if price is not None else self.data.close[0]
        if self.position.size > 0:
            return (p - self.entry_price) / self.entry_price * 100
        return (self.entry_price - p) / self.entry_price * 100

    def _incandle_rors(self):
        """캔들 고가/저가 기반 최고·최저 수익률 반환"""
        if self.position.size > 0:  # long
            best  = (self.data.high[0]  - self.entry_price) / self.entry_price * 100
            worst = (self.data.low[0]   - self.entry_price) / self.entry_price * 100
        else:  # short
            best  = (self.entry_price - self.data.low[0])  / self.entry_price * 100
            worst = (self.entry_price - self.data.high[0]) / self.entry_price * 100
        return best, worst

    def _bar_datetime(self):
        """현재 4h 봉의 시작 datetime 반환"""
        return bt.num2date(self.data.datetime[0]).replace(tzinfo=None)

    def _get_intrabar_sub(self):
        """현재 4h 봉에 해당하는 1h 서브 봉 DataFrame 반환 (없으면 None)"""
        if self.p.intrabar_data is None:
            return None
        bar_dt = pd.Timestamp(self._bar_datetime())
        end_dt = bar_dt + pd.Timedelta(hours=4)
        df = self.p.intrabar_data
        mask = (df.index >= bar_dt) & (df.index < end_dt)
        sub = df[mask].sort_index()
        return sub if len(sub) > 0 else None

    def _resolve_trend_stop(self, old_stop_ror):
        """
        추세추종: 4h 캔들 내 고가가 트레일링 스탑을 올리기 전에
        저가가 구 손절선을 먼저 터치했는지 1h로 판별.

        Returns: 'stop_first' | 'high_first'
        """
        sub = self._get_intrabar_sub()
        if sub is None:
            return 'stop_first'  # 1h 데이터 없으면 보수적으로 손절 우선

        old_stop_price = self.entry_price * (1 + old_stop_ror / 100)
        is_long = self.position.size > 0

        for _, row in sub.iterrows():
            if is_long:
                if row['Low'] <= old_stop_price:
                    return 'stop_first'
                # 고가가 highest_ror를 새로 경신하면 high_first
                cur_high_ror = (row['High'] - self.entry_price) / self.entry_price * 100
                if cur_high_ror > self.highest_ror:
                    return 'high_first'
            else:
                if row['High'] >= old_stop_price:
                    return 'stop_first'
                cur_low_ror = (self.entry_price - row['Low']) / self.entry_price * 100
                if cur_low_ror > self.highest_ror:
                    return 'high_first'

        return 'stop_first'

    def _resolve_mr_exit(self, target_ror, stop_ror):
        """
        평균회귀: 4h 캔들 내 목표가와 손절가가 동시에 터치될 때
        1h로 선후 판별.

        Returns: 'target_first' | 'stop_first'
        """
        sub = self._get_intrabar_sub()
        if sub is None:
            return 'stop_first'  # 보수적

        is_long = self.position.size > 0
        target_price = self.entry_price * (1 + target_ror / 100)
        stop_price   = self.entry_price * (1 + stop_ror   / 100)

        for _, row in sub.iterrows():
            if is_long:
                if row['High'] >= target_price:
                    return 'target_first'
                if row['Low'] <= stop_price:
                    return 'stop_first'
            else:
                if row['Low'] <= target_price:
                    return 'target_first'
                if row['High'] >= stop_price:
                    return 'stop_first'

        return 'stop_first'

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
        is_trending = self._check_trend_strength()
        slope = self._calc_regression_slope()

        if is_trending and slope > self.p.slope_threshold:
            return 'uptrend'
        elif is_trending and slope < -self.p.slope_threshold:
            return 'downtrend'
        return 'ranging'

    def _check_trend_entry(self):
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

        size = (self.broker.get_cash() * self.p.risk_percent) / risk_per_unit
        if size <= 0:
            return

        if direction == 'long':
            self.buy(size=size)
        else:
            self.sell(size=size)

        self._pending_entry = {
            'atr_val': atr_val,
            'mode': mode,
        }

    def notify_order(self, order):
        if order.status == order.Completed and self._pending_entry is not None:
            info = self._pending_entry
            self._pending_entry = None
            fill_price = order.executed.price
            self._reset()
            self.entry_price = fill_price
            self.entry_atr = info['atr_val']
            self.trade_mode = info['mode']
            if info['mode'] == 'mean_reversion':
                self.stop_loss_ror = self.p.mr_stop_loss
            else:
                self.stop_loss_ror = -(info['atr_val'] * self.p.atr_multiplier) / fill_price * 100
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._pending_entry = None

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

            # 캔들 고가/저가 기반 최고·최저 수익률
            incandle_best, incandle_worst = self._incandle_rors()

            # ── 평균회귀 모드 청산 ────────────────────────────────
            if self.trade_mode == 'mean_reversion':
                target_hit = incandle_best  >= self.p.mr_target_ror
                stop_hit   = incandle_worst <= self.p.mr_stop_loss

                if target_hit and stop_hit:
                    # 캔들 내 동시 터치 → 1h로 선후 판별
                    result = self._resolve_mr_exit(self.p.mr_target_ror, self.p.mr_stop_loss)
                    if result in ('target_first', 'stop_first'):
                        self.close()
                        self._reset()
                elif target_hit or stop_hit:
                    self.close()
                    self._reset()
                elif self.bars_in_trade > self.p.mr_time_exit_bars:
                    self.close()
                    self._reset()
                return

            # ── 추세추종 모드 청산 ────────────────────────────────
            old_stop_ror = self.stop_loss_ror

            # 트레일링 스탑 업데이트: 캔들 내 고가(최고 수익) 기준
            self._update_trailing_stop(incandle_best)
            new_stop_ror = self.stop_loss_ror

            should_close = False
            is_hard_stop = False

            if incandle_worst < old_stop_ror:
                # 구 손절선 아래로 저가가 내려감 → 무조건 청산
                should_close = True
                if not self.trailing_active:
                    is_hard_stop = True

            elif incandle_worst < new_stop_ror and new_stop_ror > old_stop_ror:
                # 저가가 구 손절선 위 / 신 손절선 아래 → 1h로 고점 vs 저점 선후 판별
                result = self._resolve_trend_stop(old_stop_ror)
                if result == 'stop_first':
                    # 저가가 먼저 → 구 손절선 기준 청산, 트레일링 되돌리기
                    self.stop_loss_ror = old_stop_ror
                    should_close = True
                # else: 고점이 먼저 → 신 손절선 적용, 저가는 그 위 → 청산 안 함

            if not should_close and self._check_volatility_exit():
                should_close = True
            if not should_close and self._check_time_exit():
                should_close = True

            if should_close:
                if not is_hard_stop and self._should_hold():
                    return
                self.close()
                self._reset()
