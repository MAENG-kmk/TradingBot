from datetime import datetime, timedelta
import pandas as pd

def getData(client, symbol, type, limit):
  if type == '1d':
    start_time = (datetime.now() - timedelta(days=limit)).strftime("%d %b %Y %H:%M:%S")
  elif type == '1h':
    start_time = (datetime.now() - timedelta(hours=limit+12)).strftime("%d %b %Y %H:%M:%S")
  elif type == '4h':
    start_time = (datetime.now() - timedelta(hours=4*(limit+12))).strftime("%d %b %Y %H:%M:%S")
  elif type == '1w':
    start_time = (datetime.now() - timedelta(weeks=limit)).strftime("%d %b %Y %H:%M:%S")
  else:
    start_time = (datetime.now() - timedelta(days=3)).strftime("%d %b %Y %H:%M:%S")
    
  candles = client.futures_historical_klines(
    symbol=symbol,
    interval=type,
    start_str=start_time
  )
  
  df = pd.DataFrame(data=candles, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Open'] - df['Close']
  df.set_index('time', inplace=True)
  df = df.drop(labels='a',axis=1)
  df = df.drop(labels='b',axis=1)
  df = df.drop(labels='c',axis=1)
  df = df.drop(labels='d',axis=1)
  df = df.drop(labels='e',axis=1)
  df = df.drop(labels='f',axis=1)
  df = df.astype('float64')
  df = df.astype({'Volume': 'int64'})
  df.index.name = None
  return df[-limit:]