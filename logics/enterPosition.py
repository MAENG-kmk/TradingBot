import math

def checkOverlap(positions, symbol):
  for position in positions:
    if position['symbol'] == symbol:
      return True
  return False


def enterPosition(client, side, ticker, total_balance, available_balance, positions, position_info, getData, getRsi, getMa_diff, getVolume, getLarry, setLeverage, createOrder):
  revision = 0.99
  bullet = float(total_balance)/10 * revision
  bullets = float(available_balance) // bullet
  enter_list = []
  black_list = []
  if side == 'long':
    ticker = ticker.iloc[::-1]
    for _, coin in ticker.iterrows():
      symbol = coin['symbol']
      data = getData(client, symbol, '1d', 30)
      if len(data) < 28:
        continue
      check_volume = getVolume(data)
      if not check_volume or symbol[-4:] != 'USDT' or symbol in black_list:
        continue
      else:
        ma_diff = getMa_diff(data)
        rsi = getRsi(data)
        larry = getLarry(data)
        # rsi 걍 90으로 해놓은 상태
        if ma_diff == 'long' and larry == 'long' and rsi < 90 and int(rsi) != 99:
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
            response = createOrder(client, symbol, 'BUY', 'MARKET', amount)
            if response == False:
              black_list.append(symbol)
            else:
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
      check_volume = getVolume(data)
      if not check_volume or symbol[-4:] != 'USDT' or symbol in black_list:
        continue
      else:
        ma_diff = getMa_diff(data)
        rsi = getRsi(data)
        larry = getLarry(data)
        if ma_diff == 'short' and larry == 'short' and rsi > 10 and int(rsi) != 99:
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
            response = createOrder(client, symbol, 'SELL', 'MARKET', amount)
            if response == False:
              black_list.append(symbol)
            else: 
              position_info[symbol] = [side, rsi]
              enter_list.append(symbol)
      if len(enter_list) == bullets:
        break
    
    
  return 