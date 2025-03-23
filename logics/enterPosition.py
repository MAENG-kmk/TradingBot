import math

def checkOverlap(positions, symbol):
  for position in positions:
    if position['symbol'] == symbol:
      return True
  return False


def logic_filter(data, logiclist):
  result = 'None'
  for logic in logiclist:
    side = logic(data)
    if side == result:
      continue
    elif  result == 'None':
      result = side
    else:
      result = 'None'
      break
    
  return result


def enterPosition(client, ticker, total_balance, available_balance, positions, position_info, logic_list, getUsaTimeData, getVolume, setLeverage, createOrder, betController):
  revision = 0.99
  bullet = float(total_balance)/10 * revision
  bullets = float(available_balance) // bullet
  enter_list = []
  black_list = []

  for _, coin in ticker.iterrows():
    symbol = coin['symbol']
    data = getUsaTimeData(client, symbol, 50)
    if len(data) < 49:
      continue
    check_volume = getVolume(data)
    if not check_volume or symbol[-4:] != 'USDT' or symbol in black_list:
      continue
    else:
      way = logic_filter(data, logic_list)
      
      ######################################## 테스트 시 활성화 #############################################
      # if way != 'None':
      #   print('symbol:', symbol)
      #   print('way:', way)
      #   print('------------------------------------------------')
      # way = 'none'
      # bullets = 100
      ###################################################################################################
      
      if way == 'long':
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
            betController.saveNew(symbol)
            position_info[symbol] = [way, 0]
            enter_list.append(symbol)
            
            
      elif way == 'short':
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
            betController.saveNew(symbol)
            position_info[symbol] = [way, 0]
            enter_list.append(symbol)
            
            
    if len(enter_list) == bullets:
      break
    
  return 