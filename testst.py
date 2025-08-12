import pandas as pd
import numpy as np
from binance.client import Client
from datetime import datetime, timedelta
import time
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET

# Binance API 키 설정 (사용자 자신의 키로 교체)
API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_API_SECRET

# Binance 클라이언트 초기화
client = Client(API_KEY, API_SECRET)

# Binance Futures에서 PERPETUAL USDT 페어 심볼 목록 가져오기
def get_futures_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = [
        s['symbol'] for s in exchange_info['symbols']
        if s['contractType'] == 'PERPETUAL' and s['quoteAsset'] == 'USDT'
    ]
    return symbols

# 역사적 가격 데이터 다운로드 (예: 최근 365일, 일봉)
def get_historical_data(symbols, interval='1d', limit=365):
    end_time = datetime.now()
    start_time = end_time - timedelta(days=limit)
    start_str = start_time.strftime('%Y-%m-%d')

    df_dict = {}
    for symbol in symbols:
        try:
            klines = client.futures_historical_klines(symbol, interval, start_str)
            if klines:
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df['close'] = pd.to_numeric(df['close'])
                df_dict[symbol] = df['close']
            time.sleep(0.1)  # API rate limit 방지
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
    
    # 모든 심볼의 close 가격을 하나의 DataFrame으로 병합
    price_df = pd.DataFrame(df_dict)
    return price_df

# 로그 수익률 계산
def calculate_log_returns(price_df):
    log_returns = np.log(price_df / price_df.shift(1))
    return log_returns.dropna()

# 상관관계 행렬 계산 및 높은 상관관계 쌍 찾기 (threshold 이상)
def find_correlated_pairs(returns, threshold=0.8):
    corr_matrix = returns.corr()
    pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            corr = corr_matrix.iloc[i, j]
            if corr > threshold:
                pair = (corr_matrix.columns[i], corr_matrix.columns[j], corr)
                pairs.append(pair)
    
    # 상관관계 내림차순 정렬
    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs

# 메인 실행

symbols = get_futures_symbols()
print(f"Found {len(symbols)} USDT Perpetual Futures symbols.")

# 데이터 다운로드 (시간이 걸릴 수 있음)
price_df = get_historical_data(symbols)

# 로그 수익률 계산
returns = calculate_log_returns(price_df)

# 상관관계 높은 쌍 찾기
correlated_pairs = find_correlated_pairs(returns, threshold=0.8)

print("Highly correlated pairs (correlation > 0.8):")
for pair in correlated_pairs:
    print(f"{pair[0]} - {pair[1]}: {pair[2]:.4f}")