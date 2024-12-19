import asyncio

def closePosition(client, createOrder, positions, position_info, getBalance, send_message):
  message = ""
  for position in positions:
    if position['ror'] > 5 or position['ror'] < -5:
      if position['side'] == 'long':
        createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
      else:
        createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
      info = position_info[position['symbol']]
      position_info.pop(position['symbol'], None)
      balance, _ = float(getBalance(client))
      message += "symbol: {}, ror: {:.2f}%, profit: {:.2f}$ balance: {:.2f} \n side: {}, entered rsi: {} \n\n".format(position['symbol'], position['ror'], position['profit'], balance, info[0], info[1])
  if len(message) > 0:
    asyncio.run(send_message(message))