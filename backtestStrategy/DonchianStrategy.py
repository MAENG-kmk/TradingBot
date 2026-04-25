# backtestStrategy/DonchianStrategy.py
import backtrader as bt


class DonchianStrategy(bt.Strategy):
    """
    Donchian Channel Breakout — 롱/숏 양방향
    진입: N봉 최고가/최저가 돌파
    청산: M봉 반대 채널 돌파 또는 ATR 손절
    """
    params = dict(
        entry_period=20,
        exit_period=10,
        atr_period=14,
        atr_stop_mult=2.0,
    )

    def __init__(self):
        high = self.data.high
        low  = self.data.low

        self.entry_high = bt.ind.Highest(high, period=self.p.entry_period)
        self.entry_low  = bt.ind.Lowest(low,   period=self.p.entry_period)
        self.exit_high  = bt.ind.Highest(high, period=self.p.exit_period)
        self.exit_low   = bt.ind.Lowest(low,   period=self.p.exit_period)
        self.atr        = bt.ind.ATR(self.data, period=self.p.atr_period)

        self._side       = None
        self._stop_price = None

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def _enter_long(self):
        size = self._full_size()
        self.buy(size=size)
        self._side       = 'long'
        self._stop_price = self.data.close[0] - self.atr[0] * self.p.atr_stop_mult

    def _enter_short(self):
        size = self._full_size()
        self.sell(size=size)
        self._side       = 'short'
        self._stop_price = self.data.close[0] + self.atr[0] * self.p.atr_stop_mult

    def next(self):
        price = self.data.close[0]

        if not self.position:
            # entry_high/low[-1] = 전봉 기준 N봉 최고/최저 (lookahead 방지)
            if price > self.entry_high[-1]:
                self._enter_long()
            elif price < self.entry_low[-1]:
                self._enter_short()
            return

        if self._side == 'long':
            if price < self.exit_low[-1] or price < self._stop_price:
                self.close()
                self._side = None
                if price < self.entry_low[-1]:
                    self._enter_short()
        elif self._side == 'short':
            if price > self.exit_high[-1] or price > self._stop_price:
                self.close()
                self._side = None
                if price > self.entry_high[-1]:
                    self._enter_long()
