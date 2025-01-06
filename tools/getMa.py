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