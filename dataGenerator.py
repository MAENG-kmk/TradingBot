from binance.client import Client
import pandas as pd
import time
from datetime import datetime
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

# 2021년 1월 1일부터 시작
start_date = datetime(2021, 1, 1, 0, 0, 0)
startTime = int(start_date.timestamp() * 1000)  # 밀리초 단위

# 최대한 많은 데이터 가져오기 (루프로 여러 번 요청)
all_klines = []
max_requests = 20  # 최대 50번 요청 (1500 × 50 = 75,000개 = 약 12년분)

print(f"ETHUSDT 4시간 봉 데이터 수집 중... (2021년부터)")
print(f"시작 시간: {datetime.fromtimestamp(startTime/1000)}")

for i in range(max_requests):
    try:
        klines = client.futures_klines(
            symbol='ETHUSDT',
            interval=client.KLINE_INTERVAL_4HOUR,
            limit=1500,
            startTime=startTime
        )
        
        if not klines:
            print(f"더 이상 데이터 없음 (현재까지)")
            break
        
        all_klines.extend(klines)
        
        # 다음 요청을 위해 마지막 캔들의 시간을 저장 (다음 캔들부터 시작)
        startTime = klines[-1][0] + 1
        
        last_date = datetime.fromtimestamp(klines[-1][0]/1000)
        print(f"진행: {i+1}/{max_requests} - 총 {len(all_klines)}개 - 마지막: {last_date}")
        
        # API 요청 제한 회피 (1초 대기)
        time.sleep(1)
        
    except Exception as e:
        print(f"에러 발생: {e}")
        break

print(f"\n✅ 총 {len(all_klines)}개 데이터 수집 완료!")

# DataFrame으로 정리
df = pd.DataFrame(all_klines, columns=[
    'timestamp', 'Open', 'High', 'Low', 'Close', 'Volume',
    'Close_time', 'Quote_asset_volume', 'Number_of_trades',
    'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
])

df['Date'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('Date', inplace=True)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

# 중복 제거
df = df[~df.index.duplicated(keep='first')]

print(f"기간: {df.index.min()} ~ {df.index.max()}")
print(f"행: {len(df)}")

# 저장
dataName = "ETHUSDT_4h"
df.to_csv('backtestDatas/' + dataName + '.csv')
print(f"저장 완료: backtestDatas/{dataName}.csv")