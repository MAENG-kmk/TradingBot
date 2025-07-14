from datetime import datetime, timedelta
import pandas as pd

def getData_1(client, symbol, type, limit):
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
  df['Body'] = df['Close'] - df['Open']
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

def getData(client, symbol, type, limit):
  klines = client.futures_klines(
    symbol=symbol, 
    interval=client.KLINE_INTERVAL_1DAY, 
    limit=limit
  )
  df = pd.DataFrame(data=klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Close'] - df['Open']
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
  return df

def get1HData(client, symbol, limit):
  klines = client.futures_klines(
    symbol=symbol, 
    interval=client.KLINE_INTERVAL_1HOUR, 
    limit=limit
  )
  df = pd.DataFrame(data=klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Close'] - df['Open']
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
  return df

def get1MData(client, symbol, limit):
  klines = client.futures_klines(
    symbol=symbol, 
    interval=client.KLINE_INTERVAL_1MINUTE, 
    limit=limit
  )
  df = pd.DataFrame(data=klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Close'] - df['Open']
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
  return df

def get4HData(client, symbol, limit):
  klines = client.futures_klines(
    symbol=symbol, 
    interval=client.KLINE_INTERVAL_4HOUR, 
    limit=limit
  )
  df = pd.DataFrame(data=klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Close'] - df['Open']
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
  return df

def getUsaTimeData(client, symbol, limit):
  klines = client.futures_klines(
    symbol=symbol, 
    interval=client.KLINE_INTERVAL_1HOUR, 
    limit=limit*24+1
  )
  df = pd.DataFrame(data=klines, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume', 'a', 'b', 'c', 'd', 'e', 'f'])
  df['time'] = pd.to_datetime(df['time'], unit='ms')
  df['Open'] = pd.to_numeric(df['Open'])
  df['Close'] = pd.to_numeric(df['Close'])
  df['Body'] = df['Close'] - df['Open']
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
  
  data_1h = df
  if len(data_1h) < limit*24:
    return []
  data = []
  cur_hour = datetime.now().hour
  start = 24 + (int(cur_hour) - 23) + 1
  for i in range(limit-1):
    high = max(data_1h.iloc[-start-24*(limit-1-i):-start-24*(limit-1-i-1)]['High'])
    low = min(data_1h.iloc[-start-24*(limit-1-i):-start-24*(limit-1-i-1)]['Low'])
    volume = sum(data_1h.iloc[-start-24*(limit-1-i):-start-24*(limit-1-i-1)]['Volume'])
    open = data_1h.iloc[-start-24*(limit-1-i)]['Open']
    close = data_1h.iloc[-start-24*(limit-1-i-1)]['Open']
    data.append([open, high, low, close, volume])
  last_data = data_1h.iloc[-start:]
  open = data_1h.iloc[-start]['Open']
  high = max(last_data['High'])
  low = min(last_data['Low'])
  close = data_1h.iloc[-1]['Close']
  volume = sum(last_data['Volume'])
  data.append([open, high, low, close, volume])
  df = pd.DataFrame(data=data, columns=['Open', 'High', 'Low', 'Close', 'Volume'])
  df['Body'] = df['Close'] - df['Open']

  return df