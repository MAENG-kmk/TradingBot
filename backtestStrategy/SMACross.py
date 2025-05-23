import backtrader as bt


class SMACross(bt.Strategy):
  def __init__(self):
    self.sma_short = bt.ind.SMA(period=3)
    self.sma_long = bt.ind.SMA(period=5)

  def next(self):
    if not self.position:
      if self.sma_short[0] > self.sma_long[0] and self.data.close > self.sma_short[0]:
        self.buy()
      elif self.sma_short[0] < self.sma_long[0] and self.data.close < self.sma_short[0]:
        self.sell()
    else:
      if self.position.size > 0:
        if self.data.close < self.sma_short[0]:
          self.close()
      else:
        if self.data.close > self.sma_short[0]:
          self.close()
