from binance.exceptions import BinanceAPIException

def makeIsolated(client, symbol):
  try:
      response = client.futures_change_margin_type(
          symbol=symbol,
          marginType='ISOLATED' 
      )
  except BinanceAPIException as e:
      if "No need to change margin type" not in str(e):
          print("에러 발생:", e)