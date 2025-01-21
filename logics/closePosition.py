import asyncio

def closePosition(client, createOrder, positions, position_info, winnig_history, getBalance, send_message):
  message = ""
  for position in positions:
    if position['ror'] > 7:
      if position['side'] == 'long':
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
        winnig_history[0] += 1
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
        winnig_history[2] += 1
    elif position['ror'] < -5:
      if position['side'] == 'long':
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
        winnig_history[1] += 1
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
        winnig_history[3] += 1
      
      if response:
        if position['symbol'] in position_info:
          info = position_info.pop(position['symbol'], None)
        else:
          info = [0, 0]
        balance, _ = getBalance(client)
        message += "symbol: {}, ror: {:.2f}%, profit: {:.2f}$ balance: {:.2f} \n side: {}, entered rsi: {:.2f}, {} \n\n".format(position['symbol'], position['ror'], position['profit'], float(balance), info[0], info[1], winnig_history)
  if len(message) > 0:
    asyncio.run(send_message(message))