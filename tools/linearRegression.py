import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression


def linearRegression(data):
  period_long = 12
  period_middle = 6
  period_short = 3
  x = np.array([i for i in range(1, 1 + period_long)])
  y_close = np.array(data.iloc[-period_long:]['Close'])
  model_close = LinearRegression()
  
  x_middle = np.array([i for i in range(1+period_long-period_middle, 1+period_long)])
  y_middle = np.array(data.iloc[-period_middle:]['Close'])
  model_middle = LinearRegression()
  model_middle.fit(X=x_middle.reshape(-1, 1), y=y_middle)
  
  x_short = np.array([i for i in range(1+period_long-period_short, 1+period_long)])
  y_short = np.array(data.iloc[-period_short:]['Close'])
  model_short = LinearRegression()
  model_short.fit(X=x_short.reshape(-1, 1), y=y_short)

  x_li = x.reshape(-1, 1)
  
  model_close.fit(X=x_li, y=y_close)
  pred_short = model_short.predict(x_short.reshape(-1, 1))

  trend_long = model_close.coef_[0]
  trend_middle = model_middle.coef_[0]
  trend_short = model_short.coef_[0]
  curPrice = data.iloc[-1]['Close']

  if trend_long > 0 and trend_middle > 0 and trend_short > 0 and trend_short > trend_middle and trend_middle > trend_long:
    if curPrice > pred_short[-1]:
      return 'long'
  elif trend_long < 0 and trend_middle < 0 and trend_short < 0 and trend_short < trend_middle and trend_middle < trend_long:
    if curPrice < pred_short[-1]: 
      return 'short'
  else:
    return 'none'