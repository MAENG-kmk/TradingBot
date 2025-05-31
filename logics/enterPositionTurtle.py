import math

def logic_filter(data, logiclist):
  result = 'None'
  for logic in logiclist:
    side = logic(data)
    if side == 'None':
      break
    if side == result:
      continue
    elif  result == 'None':
      result = side
    else:
      result = 'None'
      break
    
  return result


def enterPositionTurtle(client, ticker, total_balance, available_balance, positions, position_info, logic_list, getData, getVolume, setLeverage, createOrder, betController, special_care):
  revision = 0.99
  bullet = float(total_balance)/10 * revision
  bullets = float(available_balance) // bullet
  if bullets == 0:
    betController.isFull = True
  enter_list = []
  black_list = []
  
  if positions:
    lastPosition = positions[-1]
    symbol = lastPosition['symbol']
    side = lastPosition['side']
    curPrice = lastPosition['markPrice']
    
    lastQty = str(lastPosition['amount']).split('.')
    if len(lastQty) == 1:
      point = 0
      amount = math.floor((bullet / float(lastPosition['markPrice'])) )
    else:
      point = len(lastQty[1])
      amount = math.floor((bullet / float(lastPosition['markPrice'])) * (10**point)) / (10**point)
    if amount < 10**(-point):
      return

    if betController.symbol == '':
      betController.saveNew(symbol, side, lastPosition['enterPrice'])
    if side == 'long':
      if curPrice > betController.firePrice:
        setLeverage(client, symbol, 1)
        response = createOrder(client, symbol, 'BUY', 'MARKET', amount)
        if response == False:
          black_list.append(symbol)
        else:
          betController.saveNew(symbol, side, curPrice)
          position_info[symbol] = [side, 0]
          enter_list.append(symbol)
    else:
      if curPrice < betController.firePrice:
        setLeverage(client, symbol, 1)
        response = createOrder(client, symbol, 'SELL', 'MARKET', amount)
        if response == False:
          black_list.append(symbol)
        else:
          betController.saveNew(symbol, side, curPrice)
          position_info[symbol] = [side, 0]
          enter_list.append(symbol)
  else:
    for _, coin in ticker.iterrows():
      symbol = coin['symbol']
      data = getData(client, symbol, 50)
      if len(data) < 49:
        continue
      check_volume = getVolume(data)
      if not check_volume or symbol[-4:] != 'USDT' or symbol in black_list:
        continue
      else:
        side = logic_filter(data, logic_list)
        if side == 'long' or side == 'short':
          curPrice = data.iloc[-1]['Close']
          break
        
    lastQty = coin['lastQty'].split('.')
    if len(lastQty) == 1:
      point = 0
      amount = math.floor((bullet / float(coin['lastPrice'])) )
    else:
      point = len(lastQty[1])
      amount = math.floor((bullet / float(coin['lastPrice'])) * (10**point)) / (10**point)
    if amount < 10**(-point):
      return
    
    if side == 'long':
      setLeverage(client, symbol, 1)
      response = createOrder(client, symbol, 'BUY', 'MARKET', amount)
      if response == False:
        black_list.append(symbol)
      else:
        betController.saveNew(symbol, side, curPrice)
        position_info[symbol] = [side, 0]
        enter_list.append(symbol)

    elif side == 'short':     
      setLeverage(client, symbol, 1)
      response = createOrder(client, symbol, 'SELL', 'MARKET', amount)
      if response == False:
        black_list.append(symbol)
      else: 
        betController.saveNew(symbol, side, curPrice)
        position_info[symbol] = [side, 0]
        enter_list.append(symbol)
          
  return 