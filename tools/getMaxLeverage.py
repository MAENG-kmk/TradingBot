
def getMaxLeverage(client, symbol):
  brackets = client.futures_leverage_bracket(symbol = symbol)[0]
  bracket = brackets['brackets'][0]
  maxLev = bracket['initialLeverage']
  return maxLev