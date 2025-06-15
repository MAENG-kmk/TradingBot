def getATR(data):
  period = 12
  data['Range'] = data['High'] - data['Low']
  atr = sum(data.iloc[-period:]['Range']) / period
  return atr