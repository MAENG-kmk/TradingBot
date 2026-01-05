"""
페어 트레이딩 진입 로직

기존 단일 코인 진입 대신 페어 쌍을 찾고 Z-Score 기반으로 진입합니다.
"""

import math
import sys
import os
import json
from datetime import datetime

sys.path.append(os.path.abspath("."))

# Pair trading 모듈 import
try:
    from pair_trading.data_fetcher import BinanceDataFetcher
    from pair_trading.cointegration_test import CointegrationTester
except ImportError:
    print("⚠️  페어 트레이딩 모듈을 찾을 수 없습니다. pair_trading/ 폴더를 확인하세요.")
    BinanceDataFetcher = None
    CointegrationTester = None


class PairTradingEntry:
    """페어 트레이딩 진입 관리"""
    
    def __init__(self, client, pairs_file='pair_trading/pair_trading_results.json'):
        """
        초기화
        
        Args:
            client: Binance client
            pairs_file: 페어 정보 JSON 파일 경로
        """
        self.client = client
        self.pairs_file = pairs_file
        self.fetcher = BinanceDataFetcher() if BinanceDataFetcher else None
        self.tester = CointegrationTester() if CointegrationTester else None
        self.pairs = []
        
        # 페어 정보 로드
        self.load_pairs()
    
    def load_pairs(self):
        """페어 정보 로드"""
        try:
            if not os.path.exists(self.pairs_file):
                print(f"⚠️  페어 파일 없음: {self.pairs_file}")
                print("   pair_finder.py를 먼저 실행하여 페어를 찾으세요.")
                return
            
            with open(self.pairs_file, 'r') as f:
                data = json.load(f)
                self.pairs = data.get('pairs', [])
            
            print(f"✓ 페어 {len(self.pairs)}개 로드됨")
        
        except Exception as e:
            print(f"❌ 페어 로드 실패: {e}")
    
    def calculate_spread_zscore(self, price1, price2, hedge_ratio, lookback=90):
        """
        스프레드 Z-Score 계산
        
        Args:
            price1, price2: 가격 시계열
            hedge_ratio: 헤징 비율
            lookback: 평균/표준편차 계산 기간
        
        Returns:
            dict: 스프레드 통계
        """
        # 스프레드 계산
        spread = price1 - hedge_ratio * price2
        
        # 최근 lookback 기간 통계
        spread_window = spread.tail(lookback)
        spread_mean = spread_window.mean()
        spread_std = spread_window.std()
        
        # 현재 Z-Score
        current_spread = spread.iloc[-1]
        zscore = (current_spread - spread_mean) / spread_std
        
        return {
            'current_spread': current_spread,
            'spread_mean': spread_mean,
            'spread_std': spread_std,
            'zscore': zscore
        }
    
    def check_entry_signal(self, pair_info, zscore_threshold=2.5, min_correlation=0.75):
        """
        진입 신호 확인
        
        Args:
            pair_info: 페어 정보
            zscore_threshold: Z-Score 임계값
            min_correlation: 최소 상관계수
        
        Returns:
            dict: 신호 정보 또는 None
        """
        symbol1 = pair_info['symbol1']
        symbol2 = pair_info['symbol2']
        hedge_ratio = pair_info['hedge_ratio']
        
        try:
            # 최신 데이터 가져오기
            data1 = self.fetcher.get_historical_klines(symbol1, interval='4h', days=90)
            data2 = self.fetcher.get_historical_klines(symbol2, interval='4h', days=90)
            
            if data1 is None or data2 is None:
                return None
            
            # 같은 인덱스로 맞추기
            common_index = data1.index.intersection(data2.index)
            if len(common_index) < 50:
                return None
            
            price1 = data1.loc[common_index]['close']
            price2 = data2.loc[common_index]['close']
            
            # 상관관계 재확인 (최근 30일)
            recent_correlation = self.tester.calculate_correlation(
                price1.tail(180),
                price2.tail(180)
            )
            
            # 상관관계 체크
            if recent_correlation < min_correlation:
                return None
            
            # Z-Score 계산
            spread_stats = self.calculate_spread_zscore(
                price1, price2, hedge_ratio
            )
            
            zscore = spread_stats['zscore']
            
            # 진입 신호 판단
            signal = None
            
            if zscore > zscore_threshold:
                # 롱 스프레드: symbol1 롱 + symbol2 숏
                signal = {
                    'type': 'LONG_SPREAD',
                    'symbol1': symbol1,
                    'symbol2': symbol2,
                    'side1': 'long',
                    'side2': 'short',
                    'zscore': zscore,
                    'hedge_ratio': hedge_ratio,
                    'correlation': recent_correlation,
                    'price1': float(price1.iloc[-1]),
                    'price2': float(price2.iloc[-1])
                }
            
            elif zscore < -zscore_threshold:
                # 숏 스프레드: symbol1 숏 + symbol2 롱
                signal = {
                    'type': 'SHORT_SPREAD',
                    'symbol1': symbol1,
                    'symbol2': symbol2,
                    'side1': 'short',
                    'side2': 'long',
                    'zscore': zscore,
                    'hedge_ratio': hedge_ratio,
                    'correlation': recent_correlation,
                    'price1': float(price1.iloc[-1]),
                    'price2': float(price2.iloc[-1])
                }
            
            return signal
        
        except Exception as e:
            print(f"❌ {symbol1}+{symbol2} 신호 체크 실패: {e}")
            return None
    
    def find_entry_signals(self, zscore_threshold=2.5):
        """
        모든 페어에서 진입 신호 찾기
        
        Args:
            zscore_threshold: Z-Score 임계값
        
        Returns:
            list: 진입 신호 목록
        """
        if not self.pairs:
            print("⚠️  로드된 페어가 없습니다.")
            return []
        
        signals = []
        
        print(f"페어 {len(self.pairs)}개 진입 신호 체크 중...")
        
        for pair in self.pairs:
            signal = self.check_entry_signal(pair, zscore_threshold)
            
            if signal:
                signals.append(signal)
                print(f"🔴 진입 신호: {signal['symbol1']}+{signal['symbol2']} "
                      f"(Z={signal['zscore']:.2f}, {signal['type']})")
        
        return signals


def checkPairOverlap(positions, symbol1, symbol2):
    """
    페어 중복 체크
    
    Args:
        positions: 현재 포지션 목록
        symbol1, symbol2: 체크할 심볼
    
    Returns:
        bool: 중복 여부
    """
    for position in positions:
        if position['symbol'] in [symbol1, symbol2]:
            return True
    return False


def enterPositionPairTrading(client, total_balance, available_balance, positions, 
                             position_info, setLeverage, createOrder, betController,
                             zscore_threshold=2.5):
    """
    페어 트레이딩 진입 로직
    
    Args:
        client: Binance client
        total_balance: 총 잔고
        available_balance: 사용 가능 잔고
        positions: 현재 포지션 목록
        position_info: 포지션 정보 dict
        setLeverage: 레버리지 설정 함수
        createOrder: 주문 생성 함수
        betController: BetController 인스턴스
        zscore_threshold: Z-Score 임계값
    
    Returns:
        None
    """
    
    # 페어 트레이딩 진입 객체 생성
    pair_entry = PairTradingEntry(client)
    
    if not pair_entry.pairs:
        print("⚠️  페어가 없어 진입하지 않습니다.")
        return
    
    # 포지션 크기 계산
    revision = 0.99
    bullet = float(total_balance) / 10 * revision  # 계정의 10%
    
    # 페어는 2개 포지션이므로 각 5%씩
    bullet_per_position = bullet / 2
    
    # 사용 가능한 페어 개수 (포지션 2개 = 1 페어)
    max_pairs = int(float(available_balance) // bullet)
    
    if max_pairs < 1:
        print("⚠️  여유 자금 부족")
        return
    
    print(f"포지션 진입 체크: 최대 {max_pairs}개 페어 가능")
    
    # 진입 신호 찾기
    signals = pair_entry.find_entry_signals(zscore_threshold)
    
    if not signals:
        print("진입 신호 없음")
        return
    
    print(f"진입 신호 {len(signals)}개 발견")
    
    # 진입 실행
    entered_count = 0
    
    for signal in signals:
        if entered_count >= max_pairs:
            print(f"최대 페어 수 도달 ({max_pairs}개)")
            break
        
        symbol1 = signal['symbol1']
        symbol2 = signal['symbol2']
        
        # 중복 체크
        if checkPairOverlap(positions, symbol1, symbol2):
            print(f"⏭️  {symbol1}+{symbol2} 이미 포지션 있음")
            continue
        
        print(f"\n🔵 페어 진입: {symbol1}+{symbol2}")
        print(f"   타입: {signal['type']}")
        print(f"   Z-Score: {signal['zscore']:.2f}")
        print(f"   상관계수: {signal['correlation']:.4f}")
        
        # 각 코인의 주문 수량 계산
        try:
            # Symbol1 수량
            amount1 = bullet_per_position / signal['price1']
            amount1 = math.floor(amount1 * 1000) / 1000  # 소수점 3자리
            
            # Symbol2 수량
            amount2 = bullet_per_position / signal['price2']
            amount2 = math.floor(amount2 * 1000) / 1000
            
            # 레버리지 설정
            setLeverage(client, symbol1, 1)
            setLeverage(client, symbol2, 1)
            
            # Symbol1 주문
            if signal['side1'] == 'long':
                response1 = createOrder(client, symbol1, 'BUY', 'MARKET', amount1)
            else:
                response1 = createOrder(client, symbol1, 'SELL', 'MARKET', amount1)
            
            # Symbol2 주문
            if signal['side2'] == 'long':
                response2 = createOrder(client, symbol2, 'BUY', 'MARKET', amount2)
            else:
                response2 = createOrder(client, symbol2, 'SELL', 'MARKET', amount2)
            
            # 양쪽 모두 성공했는지 확인
            if response1 and response2:
                # 페어 트레이딩은 목표/손절을 스프레드 기준으로
                # 기본값 사용 (5% / -2%)
                betController.saveNew(symbol1, 5)  # targetRor 5%
                betController.saveNew(symbol2, 5)
                
                # 포지션 정보 저장
                position_info[symbol1] = [signal['side1'], signal['zscore'], 'pair', symbol2]
                position_info[symbol2] = [signal['side2'], signal['zscore'], 'pair', symbol1]
                
                entered_count += 1
                
                print(f"✅ 진입 성공:")
                print(f"   {symbol1}: {signal['side1']} {amount1}")
                print(f"   {symbol2}: {signal['side2']} {amount2}")
            else:
                print(f"❌ 주문 실패")
                if response1 and not response2:
                    # Symbol1만 성공했으면 롤백 필요
                    print("   ⚠️  롤백 필요: Symbol1 청산 권장")
        
        except Exception as e:
            print(f"❌ 진입 실패: {e}")
            continue
    
    if entered_count > 0:
        print(f"\n✓ 총 {entered_count}개 페어 진입 완료")
    else:
        print("\n진입한 페어 없음")


# 기존 enterPosition과의 호환성을 위한 래퍼
def enterPosition(client, ticker, total_balance, available_balance, positions, 
                 position_info, logic_list, getData, getVolume, setLeverage, 
                 createOrder, betController, use_pair_trading=True):
    """
    진입 로직 (페어 트레이딩 또는 기존 방식)
    
    Args:
        use_pair_trading: True면 페어 트레이딩, False면 기존 방식
    """
    
    if use_pair_trading:
        print("=" * 60)
        print("페어 트레이딩 진입 로직")
        print("=" * 60)
        
        enterPositionPairTrading(
            client, total_balance, available_balance, positions,
            position_info, setLeverage, createOrder, betController
        )
    else:
        # 기존 로직 (백업용)
        print("기존 단일 코인 진입 로직")
        # 기존 코드...
        pass
