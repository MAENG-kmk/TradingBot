import asyncio

def closePosition(client, createOrder, positions, send_message):
  message = ""
  for position in positions:
    if position['ror'] > 5 or position['ror'] < -5:
      if position['side'] == 'long':
        createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
      else:
        createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
      message += "symbol: {}, ror: {:.2f}%, profit: {:.2f}$ \n".format(position['symbol'], position['ror'], position['profit'])
  if len(message) > 0:
    asyncio.run(send_message(message))