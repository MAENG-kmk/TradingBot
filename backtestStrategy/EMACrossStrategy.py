# backtestStrategy/EMACrossStrategy.py
import backtrader as bt


class EMACrossStrategy(bt.Strategy):
    """
    EMA 골든/데드크로스 진입 + ATR 트레일링 스탑 청산 — 롱/숏 양방향
    """
    params = dict(
        fast=9,
        slow=21,
        atr_period=14,
        trail_mult=3.0,
    )

    def __init__(self):
        self.ema_fast   = bt.ind.EMA(self.data.close, period=self.p.fast)
        self.ema_slow   = bt.ind.EMA(self.data.close, period=self.p.slow)
        self.cross_up   = bt.ind.CrossUp(self.ema_fast,   self.ema_slow)
        self.cross_down = bt.ind.CrossDown(self.ema_fast, self.ema_slow)
        self.atr        = bt.ind.ATR(self.data, period=self.p.atr_period)

        self._side        = None
        self._trail_stop  = None
        self._extreme     = None  # long: 최고가 / short: 최저가

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def _update_trail(self):
        if self._side == 'long':
            bar_high = self.data.high[0]
            if bar_high > self._extreme:
                self._extreme    = bar_high
                self._trail_stop = self._extreme - self.atr[0] * self.p.trail_mult
        elif self._side == 'short':
            bar_low = self.data.low[0]
            if bar_low < self._extreme:
                self._extreme    = bar_low
                self._trail_stop = self._extreme + self.atr[0] * self.p.trail_mult

    def next(self):
        price = self.data.close[0]

        if not self.position:
            if self.cross_up[0]:
                self.buy(size=self._full_size())
                self._side       = 'long'
                self._extreme    = price
                self._trail_stop = price - self.atr[0] * self.p.trail_mult
            elif self.cross_down[0]:
                self.sell(size=self._full_size())
                self._side       = 'short'
                self._extreme    = price
                self._trail_stop = price + self.atr[0] * self.p.trail_mult
            return

        self._update_trail()

        if self._side == 'long' and price < self._trail_stop:
            self.close()
            self._side = None
            if self.cross_down[0]:
                self.sell(size=self._full_size())
                self._side       = 'short'
                self._extreme    = price
                self._trail_stop = price + self.atr[0] * self.p.trail_mult

        elif self._side == 'short' and price > self._trail_stop:
            self.close()
            self._side = None
            if self.cross_up[0]:
                self.buy(size=self._full_size())
                self._side       = 'long'
                self._extreme    = price
                self._trail_stop = price - self.atr[0] * self.p.trail_mult
