# backtestStrategy/SupertrendStrategy.py
import backtrader as bt


class _SupertrendIndicator(bt.Indicator):
    """ATR 기반 Supertrend 인디케이터."""
    lines = ('supertrend', 'direction',)
    params = dict(period=10, multiplier=3.0)

    def __init__(self):
        self.atr = bt.ind.ATR(self.data, period=self.p.period)
        self._fu = None  # final upper
        self._fl = None  # final lower

    def next(self):
        hl2         = (self.data.high[0] + self.data.low[0]) / 2.0
        atr         = self.atr[0]
        basic_upper = hl2 + self.p.multiplier * atr
        basic_lower = hl2 - self.p.multiplier * atr

        if self._fu is None:
            self._fu = basic_upper
            self._fl = basic_lower
            self.lines.direction[0]  = 1.0
            self.lines.supertrend[0] = basic_lower
            return

        prev_close = self.data.close[-1]
        self._fu = basic_upper if (basic_upper < self._fu or prev_close > self._fu) else self._fu
        self._fl = basic_lower if (basic_lower > self._fl or prev_close < self._fl) else self._fl

        prev_dir = self.lines.direction[-1]
        if prev_dir == -1.0 and self.data.close[0] > self._fu:
            direction = 1.0
        elif prev_dir == 1.0 and self.data.close[0] < self._fl:
            direction = -1.0
        else:
            direction = prev_dir

        self.lines.direction[0]  = direction
        self.lines.supertrend[0] = self._fl if direction == 1.0 else self._fu


class SupertrendStrategy(bt.Strategy):
    """
    Supertrend 추세추종 — 롱/숏 양방향
    방향 전환 시 즉시 포지션 반전
    """
    params = dict(
        st_period=10,
        st_multiplier=3.0,
    )

    def __init__(self):
        self.st = _SupertrendIndicator(
            self.data,
            period=self.p.st_period,
            multiplier=self.p.st_multiplier,
        )
        self._side = None

    def _full_size(self):
        return self.broker.get_cash() / self.data.close[0]

    def next(self):
        direction      = self.st.lines.direction[0]
        prev_direction = self.st.lines.direction[-1]

        # 방향 전환 감지
        turned_up   = (prev_direction == -1.0 and direction == 1.0)
        turned_down = (prev_direction ==  1.0 and direction == -1.0)

        if not self.position:
            if turned_up:
                self.buy(size=self._full_size())
                self._side = 'long'
            elif turned_down:
                self.sell(size=self._full_size())
                self._side = 'short'
        else:
            if self._side == 'long' and turned_down:
                self.close()
                self._side = None
                self.sell(size=self._full_size())
                self._side = 'short'
            elif self._side == 'short' and turned_up:
                self.close()
                self._side = None
                self.buy(size=self._full_size())
                self._side = 'long'
