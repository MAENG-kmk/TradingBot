import asyncio

def closePosition(client, createOrder, positions, position_info, getBalance, send_message):
  message = ""
  for position in positions:
    if position['ror'] > 5 or position['ror'] < -5:
      if position['side'] == 'long':
        createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
      else:
        createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
      if position['symbol'] in position_info:
        info = position_info.pop(position['symbol'], None)
      else:
        info = [0, 0]
      balance, _ = getBalance(client)
      message += "symbol: {}, ror: {:.2f}%, profit: {:.2f}$ balance: {:.2f} \n side: {}, entered rsi: {:.2f} \n\n".format(position['symbol'], position['ror'], position['profit'], float(balance), info[0], info[1])
  if len(message) > 0:
    asyncio.run(send_message(message))