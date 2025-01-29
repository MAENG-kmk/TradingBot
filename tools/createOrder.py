def createOrder(client, symbol, side, type, quantity):
  try:
    client.futures_create_order(
      symbol=symbol,
      side=side,
      type=type,
      quantity=quantity
    )
    return True
  except Exception as e:
    print(e)
    return False