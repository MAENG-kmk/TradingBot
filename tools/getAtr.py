def getATR(data):
  period = 14
  data['Range'] = data['High'] - data['Low']
  atr = sum(data.iloc[-period:]['Range']) / period
  return atr