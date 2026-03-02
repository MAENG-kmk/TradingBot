import backtrader as bt


class CoinBacktestStrategy(bt.Strategy):
    """
    코인별 백테스트 공통 전략

    coins/<coin>/strategy.py 의 파라미터를 받아서 백테스트 실행.
    진입: EMA + RSI + MACD + ADX 추세필터
    청산: BetController 4단계 트레일링
    """
    params = dict(
        # 진입
        ema_short=10,
        ema_long=30,
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
    )

    def __init__(self):
        self.ema_short = bt.ind.EMA(self.data.close, period=self.p.ema_short)
        self.ema_long = bt.ind.EMA(self.data.close, period=self.p.ema_long)
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

    def _enter(self, direction):
        atr_val = self.atr[0]
        if direction == 'long':
            risk_per_unit = atr_val * self.p.atr_multiplier
        else:
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
        self.stop_loss_ror = init_stop_ror

    def next(self):
        if not self.position:
            if not self._check_trend_strength():
                return

            if (self.ema_short[0] > self.ema_long[0] and
                self.p.rsi_oversell < self.rsi[0] < self.p.rsi_overbuy and
                self.macd.lines.macd[0] > self.macd.lines.signal[0]):
                self._enter('long')

            elif (self.ema_short[0] < self.ema_long[0] and
                  self.p.rsi_oversell < self.rsi[0] < self.p.rsi_overbuy and
                  self.macd.lines.macd[0] < self.macd.lines.signal[0]):
                self._enter('short')
        else:
            self.bars_in_trade += 1
            ror = self._calc_ror()
            self._update_trailing_stop(ror)

            if ror < self.stop_loss_ror:
                self.close()
                self._reset()
                return
            if self._check_volatility_exit():
                self.close()
                self._reset()
                return
            if self._check_time_exit():
                self.close()
                self._reset()
                return
