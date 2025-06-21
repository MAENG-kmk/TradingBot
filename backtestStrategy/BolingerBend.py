import backtrader as bt


class BolingerBend(bt.Strategy):
    def __init__(self):
        self.bb = bt.indicators.BollingerBands(period=20, devfactor=2)
        self.targetPrice = 0
        self.stopPrice = 0
        self.targetRor = 0.05
        self.stopRor = 0.03
        
    def clear(self):
        self.targetPrice = 0
        self.stopPrice = 0
        
    def next(self):
        if not self.position:
            if self.data.close[0] > self.bb.lines.top[0]:
                self.targetPrice = self.data.close[0] * (1 + self.targetRor)
                self.stopPrice = self.data.close[0] * (1 - self.stopRor)
                self.buy()
            elif self.data.close[0] < self.bb.lines.bot[0]:
                self.targetPrice = self.data.close[0] * (1 - self.targetRor)
                self.stopPrice = self.data.close[0] * (1 + self.stopRor)
                self.sell()
        else:
            if self.position.size > 0:
                if self.data.close[0] >= self.targetPrice:
                    self.clear()
                    self.close()
                elif self.data.close[0] < self.stopPrice:
                    self.clear()
                    self.close()
            else:
                if self.data.close[0] <= self.targetPrice:
                    self.clear()
                    self.close()
                if self.data.close[0] > self.stopPrice:
                    self.clear()
                    self.close()