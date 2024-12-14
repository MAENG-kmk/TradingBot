def createOrder(client, symbol, side, type, quantity):
  client.futures_create_order(
    symbol=symbol,
    side=side,
    type=type,
    quantity=quantity
  )