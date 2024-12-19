import math

def checkOverlap(positions, symbol):
  for position in positions:
    if position['symbol'] == symbol:
      return True
  return False


def enterPosition(client, side, ticker, total_balance, available_balance, positions, position_info, getData, getRsi, setLeverage, createOrder):
  bullet = float(total_balance)/10
  bullets = float(available_balance) // bullet
  enter_list = []
  if side == 'long':
    ticker = ticker.iloc[::-1]
    for _, coin in ticker.iterrows():
      symbol = coin['symbol']
      data = getData(client, symbol, '1d', 30)
      if len(data) < 28:
        continue
      else:
        rsi = getRsi(data)
        if rsi < 40 and int(rsi) != 99:
          lastQty = coin['lastQty'].split('.')
          if len(lastQty) == 1:
            point = 0
            amount = math.floor((bullet / float(coin['lastPrice'])) )
          else:
            point = len(lastQty[1])
            amount = math.floor((bullet / float(coin['lastPrice'])) * (10**point)) / (10**point)
          if amount < 10**(-point) or checkOverlap(positions, symbol):
            continue
          else:
            setLeverage(client, symbol, 1)
            createOrder(client, symbol, 'BUY', 'MARKET', amount)
            position_info[symbol] = [side, rsi]
            enter_list.append(symbol)
      if len(enter_list) == bullets:
        break
  else:
    for _, coin in ticker.iterrows():
      symbol = coin['symbol']
      data = getData(client, symbol, '1d', 30)
      if len(data) < 28:
        continue
      else:
        rsi = getRsi(data)
        if rsi > 60 and int(rsi) != 99:
          lastQty = coin['lastQty'].split('.')
          if len(lastQty) == 1:
            point = 0
            amount = math.floor((bullet / float(coin['lastPrice'])) )
          else:
            point = len(lastQty[1])
            amount = math.floor((bullet / float(coin['lastPrice'])) * (10**point)) / (10**point)
          if amount < 10**(-point) or checkOverlap(positions, symbol):
            continue
          else:
            setLeverage(client, symbol, 1)
            print(symbol, rsi, amount)
            createOrder(client, symbol, 'SELL', 'MARKET', amount)
            position_info[symbol] = [side, rsi]
            enter_list.append(symbol)
      if len(enter_list) == bullets:
        break
    
    
  return 