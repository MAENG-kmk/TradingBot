def getPositions(client):
  positions = client.futures_position_information()
  position_list = []
  for position in positions:
    if float(position['positionAmt']) > 0:
      side = 'long'
    else:
      side = 'short'
    profit = float(position['unRealizedProfit'])
    ror = profit / float(position['initialMargin']) * 100
    
    
    position_list.append({
      'symbol': position['symbol'],
      'side': side,
      'profit': profit,
      'ror': ror,
      'amount': abs(float(position['positionAmt'])),
      'markPrice': float(position['markPrice']),
    })
  return position_list