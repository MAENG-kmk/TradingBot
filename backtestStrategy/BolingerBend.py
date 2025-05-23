import backtrader as bt


class BolingerBend(bt.Strategy):
    def __init__(self):
        self.bb = bt.indicators.BollingerBands(period=20, devfactor=2)

    def next(self):
        if not self.position:
            if self.data.close[0] > self.bb.lines.top[0]:
                self.buy()
        else:
            if self.data.close[0] < self.bb.lines.mid[0]:
                self.close()