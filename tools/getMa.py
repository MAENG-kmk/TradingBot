def getMa(data):
  closes = []
  short_period = 5
  long_period = 14
  for close in data.iloc[-20:]['Close']:
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
  for close in data.iloc[-20:]['Close']:
    closes.append(float(close))
  short_ma1 = sum(closes[-short_period-2:-2]) / short_period
  long_ma1 = sum(closes[-long_period-2:-2]) / long_period
  
  short_ma2 = sum(closes[-short_period-1:-1]) / short_period
  long_ma2 = sum(closes[-long_period-1:-1]) / long_period
  
  short_ma3 = sum(closes[-short_period:]) / short_period
  long_ma3 = sum(closes[-long_period:]) / long_period
  
  diff_1 = short_ma1 - long_ma1
  diff_2 = short_ma2 - long_ma2
  diff_3 = short_ma3 - long_ma3
  
  if diff_1 < diff_2 and diff_2 < diff_3:
    return 'long'
  elif diff_1 > diff_2 and diff_2 > diff_3:
    return 'short'
  else:
    return 'None'