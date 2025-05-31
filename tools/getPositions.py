def getPositions(client):
  positions = client.futures_position_information()
  position_list = []
  for position in positions:
    positionAmt = position['positionAmt']
    if float(positionAmt) > 0:
      side = 'long'
    else:
      side = 'short'
    profit = float(position['unRealizedProfit'])
    ror = profit / float(position['initialMargin']) * 100
    
    amount = positionAmt[1:] if positionAmt[0] == '-' else positionAmt
    
    position_list.append({
      'symbol': position['symbol'],
      'side': side,
      'profit': profit,
      'ror': ror,
      'amount': amount,
      'markPrice': float(position['markPrice']),
      'enterTime': position['updateTime'],
      'enterPrice': position['entryPrice']
    })
  return position_list