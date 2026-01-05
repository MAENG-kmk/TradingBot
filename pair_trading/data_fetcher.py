"""
Binance 데이터 수집 모듈
"""

from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
import time


class BinanceDataFetcher:
    """Binance Futures 데이터 수집"""
    
    def __init__(self, api_key=None, api_secret=None):
        """
        초기화
        
        Args:
            api_key: Binance API Key (없으면 public data만 사용)
            api_secret: Binance API Secret
        """
        self.client = Client(api_key, api_secret)
    
    def get_futures_symbols(self, quote_asset='USDT', min_volume=10000000):
        """
        Binance Futures에서 거래 가능한 심볼 목록 가져오기
        
        Args:
            quote_asset: 기준 자산 (기본: USDT)
            min_volume: 최소 24시간 거래량 (달러)
        
        Returns:
            list: 심볼 목록
        """
        try:
            exchange_info = self.client.futures_exchange_info()
            tickers = self.client.futures_ticker()
            
            # 거래량 맵 생성
            volume_map = {}
            for ticker in tickers:
                symbol = ticker['symbol']
                volume_usd = float(ticker['quoteVolume'])
                volume_map[symbol] = volume_usd
            
            symbols = []
            for symbol_info in exchange_info['symbols']:
                symbol = symbol_info['symbol']
                status = symbol_info['status']
                
                # 조건 필터링
                if (symbol.endswith(quote_asset) and 
                    status == 'TRADING' and
                    volume_map.get(symbol, 0) >= min_volume):
                    
                    symbols.append(symbol)
            
            # 거래량 순으로 정렬
            symbols.sort(key=lambda x: volume_map.get(x, 0), reverse=True)
            
            return symbols
        
        except Exception as e:
            print(f"심볼 조회 오류: {e}")
            # 기본 주요 코인 반환
            return [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 
                'ADAUSDT', 'XRPUSDT', 'DOGEUSDT', 'MATICUSDT',
                'DOTUSDT', 'LTCUSDT', 'AVAXUSDT', 'LINKUSDT'
            ]
    
    def get_historical_klines(self, symbol, interval='4h', days=90):
        """
        과거 캔들 데이터 가져오기
        
        Args:
            symbol: 심볼 (예: BTCUSDT)
            interval: 시간 간격 (1h, 4h, 1d 등)
            days: 과거 일수
        
        Returns:
            DataFrame: 가격 데이터
        """
        try:
            # 시작 시간 계산
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # 데이터 요청
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=1000
            )
            
            # DataFrame 변환
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # 데이터 타입 변환
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # 필요한 컬럼만 선택
            df = df[['timestamp', 'close', 'volume']]
            df.set_index('timestamp', inplace=True)
            
            return df
        
        except Exception as e:
            print(f"{symbol} 데이터 조회 오류: {e}")
            return None
    
    def fetch_multiple_symbols(self, symbols, interval='4h', days=90):
        """
        여러 심볼의 데이터를 한 번에 가져오기
        
        Args:
            symbols: 심볼 리스트
            interval: 시간 간격
            days: 과거 일수
        
        Returns:
            dict: {symbol: DataFrame}
        """
        data = {}
        total = len(symbols)
        
        print(f"총 {total}개 코인 데이터 수집 중...")
        
        for i, symbol in enumerate(symbols, 1):
            print(f"[{i}/{total}] {symbol} 수집 중...", end=' ')
            
            df = self.get_historical_klines(symbol, interval, days)
            
            if df is not None and len(df) > 0:
                data[symbol] = df
                print(f"✓ ({len(df)}개 캔들)")
            else:
                print("✗ (실패)")
            
            # API rate limit 고려
            time.sleep(0.1)
        
        print(f"\n수집 완료: {len(data)}/{total}개 성공")
        
        return data


if __name__ == "__main__":
    # 테스트
    fetcher = BinanceDataFetcher()
    
    # 심볼 조회
    symbols = fetcher.get_futures_symbols(min_volume=50000000)
    print(f"거래 가능 심볼: {len(symbols)}개")
    print(f"상위 10개: {symbols[:10]}")
    
    # 데이터 수집 테스트
    test_symbols = symbols[:3]
    data = fetcher.fetch_multiple_symbols(test_symbols, interval='4h', days=30)
    
    for symbol, df in data.items():
        print(f"\n{symbol}:")
        print(df.tail())
