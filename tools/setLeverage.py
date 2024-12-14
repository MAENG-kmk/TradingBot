def setLeverage(client, symbol, leverage):
  client.futures_change_leverage(symbol=symbol, leverage=leverage)