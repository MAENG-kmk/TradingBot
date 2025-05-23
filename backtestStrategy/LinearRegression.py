import backtrader as bt


class LinearRegression(bt.Indicator):
    lines = ('trend',)
    params = (('period', 20),)

    def __init__(self):
        self.addminperiod(self.p.period)

    def next(self):
        y = self.data.get(size=self.p.period)
        x = list(range(len(y)))
        if len(y) < self.p.period:
            self.lines.trend[0] = self.data[0]
        else:
            m, b = self.linreg(x, y)
            self.lines.trend[0] = m * (self.p.period - 1) + b

    def linreg(self, x, y):
        n = len(x)
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        den = sum((x[i] - x_mean) ** 2 for i in range(n))
        m = num / den if den else 0
        b = y_mean - m * x_mean
        return m, b


class LinearRegressionStrategy(bt.Strategy):
  def __init__(self):
    self.superlong = LinearRegression(self.data.close, period=20)
    self.long = LinearRegression(self.data.close, period=10)
    self.short = LinearRegression(self.data.close, period=5)

  def next(self):
    if not self.position:
      if self.long[0] > self.superlong[0] and self.short[0] > self.long[0] and self.data.close[0] > self.short[0]:
        self.buy()
      elif self.long[0] < self.superlong[0] and  self.short[0] < self.long[0] and self.data.close[0] < self.short[0]:
        self.sell()
    else:
      if self.position.size > 0:
        if self.data.close[0] < self.short[0]:
          self.close()
      else:
        if self.data.close[0] > self.short[0]:
          self.close()