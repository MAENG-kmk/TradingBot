import asyncio

def closePosition(client, createOrder, positions, position_info, winnig_history, getBalance, send_message, betController, special_care):
  message = ""
  list_to_close = betController.getClosePositions(positions)
  for position in list_to_close:
    response = False
    special_care[position['symbol']] = {
      'side': position['side'],
      'markPrice': position['markPrice']
    }
    if position['ror'] > 0:
      if position['side'] == 'long': 
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
        check_num = 0
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
        check_num = 2
    else:
      if position['side'] == 'long':
        response = createOrder(client, position['symbol'], 'SELL', 'MARKET', position['amount'])
        check_num = 1
      else:
        response = createOrder(client, position['symbol'], 'BUY', 'MARKET', position['amount'])
        check_num = 3
      
    if response:
      winnig_history[check_num] += 1
      if position['symbol'] in position_info:
        info = position_info.pop(position['symbol'], None)
      else:
        info = [0, 0]
      balance, _ = getBalance(client)
      message += " symbol: {} \n ror: {:.2f}%, profit: {:.2f}$ \n balance: {:.2f} \n entering side: {} \n {} \n\n".format(position['symbol'], position['ror'], position['profit'], float(balance), info[0], winnig_history)

  if len(message) > 0:
    asyncio.run(send_message(message))
    