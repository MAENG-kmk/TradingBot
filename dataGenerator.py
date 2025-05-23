from binance.client import Client
import pandas as pd
import time
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

# 데이터 가져오기
klines = client.futures_klines(symbol='BCHUSDT', interval=client.KLINE_INTERVAL_4HOUR, limit=1000)

# DataFrame으로 정리
df = pd.DataFrame(klines, columns=[
    'timestamp', 'Open', 'High', 'Low', 'Close', 'Volume',
    'Close_time', 'Quote_asset_volume', 'Number_of_trades',
    'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
])
df['Date'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('Date', inplace=True)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

# 저장
dataName = "bchusdt_4h"
df.to_csv('backtestDatas/' + dataName + '.csv')