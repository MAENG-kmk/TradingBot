from binance.client import Client
import pandas as pd
import time
from datetime import datetime
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)


def generate_data(symbol, interval, interval_label, max_requests=20):
    """바이낸스 선물 캔들 데이터 수집"""
    start_date = datetime(2021, 1, 1, 0, 0, 0)
    startTime = int(start_date.timestamp() * 1000)

    all_klines = []
    file_name = f"{symbol.lower()}_{interval_label}"

    print(f"\n{'='*50}")
    print(f"{symbol} {interval_label} 데이터 수집 중... (2021년부터)")

    for i in range(max_requests):
        try:
            klines = client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=1500,
                startTime=startTime
            )

            if not klines:
                break

            all_klines.extend(klines)
            startTime = klines[-1][0] + 1
            last_date = datetime.fromtimestamp(klines[-1][0] / 1000)
            print(f"  {i+1}/{max_requests} - {len(all_klines)}개 - {last_date}")
            time.sleep(0.5)

        except Exception as e:
            print(f"  에러: {e}")
            break

    if not all_klines:
        print(f"  ❌ 데이터 없음")
        return

    df = pd.DataFrame(all_klines, columns=[
        'timestamp', 'Open', 'High', 'Low', 'Close', 'Volume',
        'Close_time', 'Quote_asset_volume', 'Number_of_trades',
        'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'
    ])

    df['Date'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('Date', inplace=True)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
    df = df[~df.index.duplicated(keep='first')]

    path = f"backtestDatas/{file_name}.csv"
    df.to_csv(path)
    print(f"  ✅ {len(df)}개 저장 → {path} ({df.index.min()} ~ {df.index.max()})")


# ===== 수집 대상 =====
COINS = [
    'ETHUSDT', 'BTCUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'LINKUSDT', 'DOGEUSDT', 'AVAXUSDT', 'ARBUSDT', 'AAVEUSDT',
]

if __name__ == '__main__':
    for symbol in COINS:
        generate_data(symbol, client.KLINE_INTERVAL_4HOUR, '4h')
    print(f"\n{'='*50}")
    print("전체 수집 완료!")