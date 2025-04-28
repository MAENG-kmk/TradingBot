import pandas as pd

def getMa(data):
  closes = []
  short_period = 7
  long_period = 25
  for close in data.iloc[-30:]['Close']:
    closes.append(float(close))
  short_ma = sum(closes[-short_period:]) / short_period
  long_ma = sum(closes[-long_period:]) / long_period
  if short_ma > long_ma:
    return 'long'
  else:
    return 'short'
  
def getMa_diff(data):
  closes = []
  short_period = 5
  long_period = 14
  for close in data.iloc[-27:]['Close']:
    closes.append(float(close))
    
  short_ma = sum(closes[-short_period-3:-3]) / short_period
  long_ma = sum(closes[-long_period-3:-3]) / long_period
  
  short_ma1 = sum(closes[-short_period-2:-2]) / short_period
  long_ma1 = sum(closes[-long_period-2:-2]) / long_period
  
  short_ma2 = sum(closes[-short_period-1:-1]) / short_period
  long_ma2 = sum(closes[-long_period-1:-1]) / long_period
  
  short_ma3 = sum(closes[-short_period:]) / short_period
  long_ma3 = sum(closes[-long_period:]) / long_period
  
  gap = short_ma - long_ma
  gap_1 = short_ma1 - long_ma1
  gap_2 = short_ma2 - long_ma2
  gap_3 = short_ma3 - long_ma3
  
  diff = gap - gap_1
  diff_1 = gap_1 - gap_2
  diff_2 = gap_2 - gap_3
  
  if diff > diff_1 and diff_1 > diff_2:
    return 'long'
  elif diff < diff_1 and diff_1 < diff_2:
    return 'short'
  else:
    return 'None'
  
def getMACD(data):
  data["EMA_12"] = data["Close"].ewm(span=12, adjust=False).mean()
  data["EMA_26"] = data["Close"].ewm(span=26, adjust=False).mean()
  data["MACD"] = data["EMA_12"] - data["EMA_26"]
  data["Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
  data["signal"] = 0
  data.loc[data["MACD"] > data["Signal"], "signal"] = 1
  data.loc[data["MACD"] < data["Signal"], "signal"] = -1  
  
  cur = int(data.iloc[-1]['signal'])
  last = int(data.iloc[-2]['signal'])
  
  if cur == 1:
    return 'long'
  elif cur == -1:
    return 'short'
  