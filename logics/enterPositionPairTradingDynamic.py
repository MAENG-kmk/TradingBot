"""
동적 페어 트레이딩 진입 로직

매번 실행 시 ticker에서 코인들을 가져와 공적분 검정으로 페어를 찾고,
Z-Score 기반으로 진입합니다.
"""

import math
import sys
import os
import numpy as np
from datetime import datetime

sys.path.append(os.path.abspath("."))


class DynamicPairFinder:
    """동적 페어 찾기 및 진입"""
    
    def __init__(self, client, getData):
        """
        초기화
        
        Args:
            client: Binance client
            getData: 데이터 가져오기 함수 (get4HData)
        """
        self.client = client
        self.getData = getData
    
    def calculate_correlation(self, price1, price2):
        """
        상관계수 계산
        
        Args:
            price1, price2: 가격 시계열 (pandas Series)
        
        Returns:
            float: 상관계수
        """
        try:
            returns1 = np.log(price1 / price1.shift(1)).dropna()
            returns2 = np.log(price2 / price2.shift(1)).dropna()
            
            # 공통 인덱스
            common_idx = returns1.index.intersection(returns2.index)
            if len(common_idx) < 30:
                return 0
            
            correlation = returns1.loc[common_idx].corr(returns2.loc[common_idx])
            return correlation
        
        except Exception as e:
            return 0
    
    def calculate_hedge_ratio(self, price1, price2):
        """
        헤징 비율 계산 (선형회귀)
        
        Args:
            price1, price2: 가격 시계열
        
        Returns:
            float: 헤징 비율
        """
        try:
            # 선형회귀: price1 = beta * price2 + alpha
            # numpy polyfit 사용
            coeffs = np.polyfit(price2, price1, 1)
            hedge_ratio = coeffs[0]
            return hedge_ratio
        
        except Exception as e:
            return 1.0
    
    def engle_granger_test(self, price1, price2):
        """
        간단한 공적분 검정 (Engle-Granger)
        statsmodels 없이 간단 버전
        
        Args:
            price1, price2: 가격 시계열
        
        Returns:
            bool: 공적분 여부
        """
        try:
            # 헤징 비율 계산
            hedge_ratio = self.calculate_hedge_ratio(price1, price2)
            
            # 스프레드 계산
            spread = price1 - hedge_ratio * price2
            
            # 스프레드의 표준편차가 일정 범위 내인지 확인
            spread_std = spread.std()
            spread_mean = spread.mean()
            
            # CV (Coefficient of Variation) 체크
            if spread_mean == 0:
                return False
            
            cv = spread_std / abs(spread_mean)
            
            # CV가 너무 크면 공적분 아님
            return cv < 0.5
        
        except Exception as e:
            return False
    
    def calculate_spread_zscore(self, price1, price2, hedge_ratio):
        """
        스프레드 Z-Score 계산
        
        Args:
            price1, price2: 가격 시계열
            hedge_ratio: 헤징 비율
        
        Returns:
            float: Z-Score
        """
        try:
            spread = price1 - hedge_ratio * price2
            
            # 전체 기간 평균/표준편차
            spread_mean = spread.mean()
            spread_std = spread.std()
            
            if spread_std == 0:
                return 0
            
            # 현재 Z-Score
            current_spread = spread.iloc[-1]
            zscore = (current_spread - spread_mean) / spread_std
            
            return zscore
        
        except Exception as e:
            return 0
    
    def find_best_pairs(self, ticker, max_pairs=20, min_correlation=0.70, 
                       zscore_threshold=2.5):
        """
        최적 페어 찾기 (동적)
        
        Args:
            ticker: getTicker() 결과 (DataFrame)
            max_pairs: 최대 검사할 페어 수
            min_correlation: 최소 상관계수
            zscore_threshold: Z-Score 임계값
        
        Returns:
            list: 진입 신호가 있는 페어 목록
        """
        print("\n동적 페어 찾기 시작...")
        
        # USDT 마진 코인만 필터링
        usdt_coins = [
            row['symbol'] for _, row in ticker.iterrows() 
            if row['symbol'].endswith('USDT')
        ]
        
        # 상위 거래량 코인만 선택 (속도 최적화)
        top_coins = usdt_coins[:30]  # 상위 30개만
        
        print(f"대상 코인: {len(top_coins)}개")
        
        pairs_with_signals = []
        checked_pairs = 0
        
        # 모든 조합 검사
        for i in range(len(top_coins)):
            for j in range(i + 1, len(top_coins)):
                symbol1 = top_coins[i]
                symbol2 = top_coins[j]
                
                checked_pairs += 1
                
                try:
                    # 데이터 수집 (4시간 봉 90개)
                    data1 = self.getData(self.client, symbol1, 90)
                    data2 = self.getData(self.client, symbol2, 90)
                    
                    if len(data1) < 90 or len(data2) < 90:
                        continue
                    
                    price1 = data1['Close']
                    price2 = data2['Close']
                    
                    # 1. 상관관계 체크
                    correlation = self.calculate_correlation(price1, price2)
                    
                    if abs(correlation) < min_correlation:
                        continue
                    
                    # 2. 공적분 검정 (간단 버전)
                    if not self.engle_granger_test(price1, price2):
                        continue
                    
                    # 3. 헤징 비율 계산
                    hedge_ratio = self.calculate_hedge_ratio(price1, price2)
                    
                    # 4. Z-Score 계산
                    zscore = self.calculate_spread_zscore(price1, price2, hedge_ratio)
                    
                    # 5. 진입 신호 체크
                    if abs(zscore) > zscore_threshold:
                        signal = {
                            'symbol1': symbol1,
                            'symbol2': symbol2,
                            'lastQty1': ticker.loc[ticker.symbol==symbol1]['lastQty'].values[0],
                            'lastQty2': ticker.loc[ticker.symbol==symbol2]['lastQty'].values[0],
                            'correlation': correlation,
                            'hedge_ratio': hedge_ratio,
                            'zscore': zscore,
                            'price1': float(price1.iloc[-1]),
                            'price2': float(price2.iloc[-1])
                        }
                        
                        if zscore > zscore_threshold:
                            signal['type'] = 'LONG_SPREAD'
                            signal['side1'] = 'long'
                            signal['side2'] = 'short'
                        else:
                            signal['type'] = 'SHORT_SPREAD'
                            signal['side1'] = 'short'
                            signal['side2'] = 'long'
                        
                        pairs_with_signals.append(signal)
                        
                        print(f"✓ 페어 발견: {symbol1}+{symbol2} "
                              f"(Z={zscore:.2f}, Corr={correlation:.2f})")
                
                except Exception as e:
                    continue
                
                # 속도 제한 (너무 많이 찾지 않기)
                if len(pairs_with_signals) >= max_pairs:
                    break
            
            if len(pairs_with_signals) >= max_pairs:
                break
        
        print(f"총 {checked_pairs}개 조합 검사, {len(pairs_with_signals)}개 신호 발견")
        
        return pairs_with_signals


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


def enterPositionPairTrading(client, ticker, total_balance, available_balance, 
                             positions, position_info, getData, setLeverage, 
                             createOrder, betController, zscore_threshold=2.5,
                             max_pairs_to_find=5):
    """
    동적 페어 트레이딩 진입 로직
    
    Args:
        client: Binance client
        ticker: getTicker() 결과
        total_balance: 총 잔고
        available_balance: 사용 가능 잔고
        positions: 현재 포지션 목록
        position_info: 포지션 정보 dict
        getData: get4HData 함수
        setLeverage: 레버리지 설정 함수
        createOrder: 주문 생성 함수
        betController: BetController 인스턴스
        zscore_threshold: Z-Score 임계값
        max_pairs_to_find: 최대 찾을 페어 수
    
    Returns:
        None
    """
    
    print("=" * 70)
    print("동적 페어 트레이딩 진입")
    print("=" * 70)
    
    # 페어 파인더 생성
    pair_finder = DynamicPairFinder(client, getData)
    
    # 포지션 크기 계산
    revision = 0.99
    bullet = float(total_balance) / 10 * revision  # 계정의 10%
    bullet_per_position = bullet / 2  # 페어는 2개 포지션
    
    # 사용 가능한 페어 개수
    max_pairs = int(float(available_balance) // bullet)
    
    if max_pairs < 1:
        print("⚠️  여유 자금 부족")
        return
    
    print(f"최대 {max_pairs}개 페어 진입 가능")
    
    # 동적으로 페어 찾기
    signals = pair_finder.find_best_pairs(
        ticker=ticker,
        max_pairs=min(max_pairs, max_pairs_to_find),
        min_correlation=0.70,
        zscore_threshold=zscore_threshold
    )
    
    if not signals:
        print("진입 신호 없음")
        return
    
    print(f"\n진입 신호 {len(signals)}개 발견")
    
    # 진입 실행
    entered_count = 0
    used_symbols = set()  # 이미 사용된 코인 추적
    
    for signal in signals:
        if entered_count >= max_pairs:
            print(f"최대 페어 수 도달 ({max_pairs}개)")
            break
        
        symbol1 = signal['symbol1']
        symbol2 = signal['symbol2']
        
        # 중복 체크 (기존 포지션)
        if checkPairOverlap(positions, symbol1, symbol2):
            print(f"⏭️  {symbol1}+{symbol2} 이미 포지션 있음")
            continue
        
        # 중복 체크 (이번 루프에서 이미 사용된 코인)
        if symbol1 in used_symbols or symbol2 in used_symbols:
            print(f"⏭️  {symbol1} 또는 {symbol2} 이미 다른 페어에서 사용됨")
            continue
        
        print(f"\n🔵 페어 진입: {symbol1}+{symbol2}")
        print(f"   타입: {signal['type']}")
        print(f"   Z-Score: {signal['zscore']:.2f}")
        print(f"   상관계수: {signal['correlation']:.4f}")
        print(f"   헤징비율: {signal['hedge_ratio']:.4f}")
        
        # 각 코인의 주문 수량 계산
        try:
            # Symbol1 수량
            lastQty1 = signal['lastQty1'].split('.')
            if len(lastQty1) == 1:
              point = 0
              amount1 = math.floor((bullet / float(signal['price1'])) )
            else:
              point = len(lastQty1[1])
              amount1 = math.floor((bullet / float(signal['price1'])) * (10**point)) / (10**point)
            
            # Symbol2 수량
            lastQty2 = signal['lastQty2'].split('.')
            if len(lastQty2) == 1:
              point = 0
              amount2 = math.floor((bullet / float(signal['price2'])) )
            else:
              point = len(lastQty2[1])
              amount2 = math.floor((bullet / float(signal['price2'])) * (10**point)) / (10**point)
            
            # 최소 주문량 체크
            if amount1 < 0.001 or amount2 < 0.001:
                print(f"⏭️  주문량 너무 적음")
                continue
            
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
                # 사용된 코인으로 등록
                used_symbols.add(symbol1)
                used_symbols.add(symbol2)
                
                # BetController에 등록
                betController.saveNew(symbol1, 5)
                betController.saveNew(symbol2, 5)
                
                # 포지션 정보 저장
                position_info[symbol1] = [
                    signal['side1'], 
                    signal['zscore'], 
                    'pair', 
                    symbol2,
                    signal['hedge_ratio']
                ]
                position_info[symbol2] = [
                    signal['side2'], 
                    signal['zscore'], 
                    'pair', 
                    symbol1,
                    signal['hedge_ratio']
                ]
                
                entered_count += 1
                
                print(f"✅ 진입 성공:")
                print(f"   {symbol1}: {signal['side1']} {amount1}")
                print(f"   {symbol2}: {signal['side2']} {amount2}")
            else:
                print(f"❌ 주문 실패")
                if response1 and not response2:
                    print("   ⚠️  롤백 필요: Symbol1 청산 권장")
        
        except Exception as e:
            print(f"❌ 진입 실패: {e}")
            continue
    
    if entered_count > 0:
        print(f"\n✓ 총 {entered_count}개 페어 진입 완료")
    else:
        print("\n진입한 페어 없음")


# 메인에서 사용할 래퍼 함수
def enterPosition(client, ticker, total_balance, available_balance, positions, 
                 position_info, logic_list, getData, getVolume, setLeverage, 
                 createOrder, betController):
    """
    페어 트레이딩 진입 (main.py와 호환)
    
    기존 enterPosition 시그니처와 동일하게 유지
    """
    
    print("\n" + "=" * 70)
    print("페어 트레이딩 진입 로직 (동적 페어 찾기)")
    print("=" * 70)
    
    enterPositionPairTrading(
        client=client,
        ticker=ticker,
        total_balance=total_balance,
        available_balance=available_balance,
        positions=positions,
        position_info=position_info,
        getData=getData,  # get4HData
        setLeverage=setLeverage,
        createOrder=createOrder,
        betController=betController,
        zscore_threshold=2.5,
        max_pairs_to_find=5
    )
