import asyncio
import sys
import os
from datetime import datetime
sys.path.append(os.path.abspath("."))
from MongoDB_python.client import addDataToMongoDB

def closePosition(client, createOrder, positions, getBalance, betController):
  datas = []
  list_to_close = betController.getClosePositions(positions)
  print(list_to_close)
  for position in list_to_close:
    response = False
    if position['ror'] > 0:
      if position['side'] == 'long': 
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
    else:
      if position['side'] == 'long':
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
      
    if response:
      data = position
      data['closeTime'] = int(datetime.now().timestamp())
      balance, _ = getBalance(client)
      data['balance'] = balance
      datas.append(data)
      
      # winnig_history[check_num] += 1
      # if position['symbol'] in position_info:
      #   info = position_info.pop(position['symbol'], None)
      # else:
      #   info = [0, 0]
      # message += " symbol: {} \n ror: {:.2f}%, profit: {:.2f}$ \n balance: {:.2f} \n entering side: {} \n {} \n\n".format(position['symbol'], position['ror'], position['profit'], float(balance), info[0], winnig_history)

  if datas:
    addDataToMongoDB(datas)