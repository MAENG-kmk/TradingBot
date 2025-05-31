import backtrader as bt

class TurtleStrategy(bt.Strategy):
    params = dict(
        entry_period=20,
        exit_period=10,
        atr_period=20,
        risk_percent=0.01,  # 계좌의 1%만 리스크로
        atr_multiplier=2
    )

    def __init__(self):
        self.high_entry = bt.ind.Highest(self.data.high, period=self.p.entry_period)
        self.low_exit = bt.ind.Lowest(self.data.low, period=self.p.exit_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.sma_short = bt.ind.SMA(period=3)
        self.sma_long = bt.ind.SMA(period=5)


    def next(self):

        cash = self.broker.get_cash()
        size = 0

        # 포지션 없을 때 진입 조건
        if not self.position:
            if self.data.close[0] > self.sma_long[0]:
                atr = self.atr[0]
                stop_loss_price = self.data.close[0] - self.p.atr_multiplier * atr

                risk_per_unit = self.data.close[0] - stop_loss_price
                units = (cash * self.p.risk_percent) / risk_per_unit
                size = float(units)

                self.buy(size=size)
                self.stop_price = stop_loss_price
                print(f"BUY: {self.data.datetime.date(0)}, Price: {self.data.close[0]:.2f}, Size: {size}")

        else:
            # 청산 조건 1: 10일 최저가 하락 시
            # if self.data.close[0] < self.sma_short[0]:
            #     self.close()
            #     print(f"EXIT (10일 최저 하락): {self.data.datetime.date(0)}, Price: {self.data.close[0]:.2f}")

            # 청산 조건 2: ATR 기반 손절
            if self.data.close[0] < self.stop_price:
                self.close()
                print(f"STOP LOSS (ATR): {self.data.datetime.date(0)}, Price: {self.data.close[0]:.2f}")

