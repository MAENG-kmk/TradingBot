"""
공적분 검정 모듈
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen


class CointegrationTester:
    """공적분 검정 및 쌍 선택"""
    
    def __init__(self, significance_level=0.05):
        """
        초기화
        
        Args:
            significance_level: 유의수준 (기본 0.05 = 5%)
        """
        self.significance_level = significance_level
    
    def engle_granger_test(self, price1, price2):
        """
        Engle-Granger 공적분 검정
        
        Args:
            price1: 첫 번째 자산 가격 시계열
            price2: 두 번째 자산 가격 시계열
        
        Returns:
            dict: 검정 결과
        """
        try:
            # 공적분 검정
            score, pvalue, crit_values = coint(price1, price2)
            
            is_cointegrated = pvalue < self.significance_level
            
            # 강도 평가
            if pvalue < 0.01:
                strength = '매우 강함'
            elif pvalue < 0.03:
                strength = '강함'
            elif pvalue < 0.05:
                strength = '보통'
            else:
                strength = '약함'
            
            return {
                'is_cointegrated': is_cointegrated,
                'pvalue': pvalue,
                'score': score,
                'critical_values': {
                    '1%': crit_values[0],
                    '5%': crit_values[1],
                    '10%': crit_values[2]
                },
                'strength': strength
            }
        
        except Exception as e:
            print(f"공적분 검정 오류: {e}")
            return None
    
    def calculate_correlation(self, price1, price2):
        """
        피어슨 상관계수 계산
        
        Args:
            price1, price2: 가격 시계열
        
        Returns:
            float: 상관계수
        """
        try:
            # 로그 수익률
            returns1 = np.log(price1 / price1.shift(1)).dropna()
            returns2 = np.log(price2 / price2.shift(1)).dropna()
            
            # 상관계수
            correlation = returns1.corr(returns2)
            
            return correlation
        
        except Exception as e:
            print(f"상관계수 계산 오류: {e}")
            return None
    
    def calculate_hedge_ratio(self, price1, price2):
        """
        헤징 비율 계산 (선형회귀)
        
        Args:
            price1, price2: 가격 시계열
        
        Returns:
            float: 헤징 비율 (beta)
        """
        try:
            # 선형회귀: price1 = alpha + beta * price2
            from scipy.stats import linregress
            
            slope, intercept, r_value, p_value, std_err = linregress(
                price2, price1
            )
            
            return slope
        
        except Exception as e:
            print(f"헤징 비율 계산 오류: {e}")
            return None
    
    def calculate_spread_stats(self, price1, price2, hedge_ratio=None):
        """
        스프레드 통계 계산
        
        Args:
            price1, price2: 가격 시계열
            hedge_ratio: 헤징 비율 (None이면 자동 계산)
        
        Returns:
            dict: 스프레드 통계
        """
        try:
            if hedge_ratio is None:
                hedge_ratio = self.calculate_hedge_ratio(price1, price2)
            
            # 스프레드 계산
            spread = price1 - hedge_ratio * price2
            
            # 통계
            spread_mean = spread.mean()
            spread_std = spread.std()
            
            # 현재 Z-Score
            current_zscore = (spread.iloc[-1] - spread_mean) / spread_std
            
            # 평균회귀 테스트 (Augmented Dickey-Fuller)
            from statsmodels.tsa.stattools import adfuller
            adf_result = adfuller(spread.dropna())
            
            is_stationary = adf_result[1] < 0.05
            
            return {
                'spread_mean': spread_mean,
                'spread_std': spread_std,
                'current_zscore': current_zscore,
                'hedge_ratio': hedge_ratio,
                'is_stationary': is_stationary,
                'adf_pvalue': adf_result[1]
            }
        
        except Exception as e:
            print(f"스프레드 통계 계산 오류: {e}")
            return None
    
    def find_cointegrated_pairs(self, price_data, min_correlation=0.70):
        """
        모든 조합에서 공적분 쌍 찾기
        
        Args:
            price_data: dict, {symbol: price_series}
            min_correlation: 최소 상관계수 (사전 필터링용)
        
        Returns:
            list: 공적분 쌍 목록
        """
        symbols = list(price_data.keys())
        cointegrated_pairs = []
        
        total_pairs = len(symbols) * (len(symbols) - 1) // 2
        print(f"\n총 {total_pairs}개 조합 검사 중...")
        
        checked = 0
        for i in range(len(symbols)):
            for j in range(i+1, len(symbols)):
                symbol1 = symbols[i]
                symbol2 = symbols[j]
                
                checked += 1
                if checked % 10 == 0:
                    print(f"진행: {checked}/{total_pairs} ({checked/total_pairs*100:.1f}%)")
                
                price1 = price_data[symbol1]['close']
                price2 = price_data[symbol2]['close']
                
                # 같은 길이로 맞추기
                common_index = price1.index.intersection(price2.index)
                if len(common_index) < 50:  # 최소 50개 데이터 필요
                    continue
                
                price1 = price1.loc[common_index]
                price2 = price2.loc[common_index]
                
                # 1단계: 상관계수 필터링
                correlation = self.calculate_correlation(price1, price2)
                if correlation is None or correlation < min_correlation:
                    continue
                
                # 2단계: 공적분 검정
                coint_result = self.engle_granger_test(price1, price2)
                if coint_result is None or not coint_result['is_cointegrated']:
                    continue
                
                # 3단계: 스프레드 분석
                spread_stats = self.calculate_spread_stats(price1, price2)
                if spread_stats is None:
                    continue
                
                # 결과 저장
                pair_info = {
                    'symbol1': symbol1,
                    'symbol2': symbol2,
                    'correlation': correlation,
                    'pvalue': coint_result['pvalue'],
                    'strength': coint_result['strength'],
                    'hedge_ratio': spread_stats['hedge_ratio'],
                    'current_zscore': spread_stats['current_zscore'],
                    'is_stationary': spread_stats['is_stationary'],
                    'adf_pvalue': spread_stats['adf_pvalue'],
                    'score': self._calculate_pair_score(
                        correlation, 
                        coint_result['pvalue'],
                        spread_stats['is_stationary']
                    )
                }
                
                cointegrated_pairs.append(pair_info)
        
        # 점수 순으로 정렬
        cointegrated_pairs.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"\n공적분 쌍 발견: {len(cointegrated_pairs)}개")
        
        return cointegrated_pairs
    
    def _calculate_pair_score(self, correlation, pvalue, is_stationary):
        """
        쌍의 품질 점수 계산
        
        Returns:
            float: 점수 (높을수록 좋음)
        """
        # 기본 점수
        score = 0
        
        # 상관계수 점수 (0~30점)
        score += correlation * 30
        
        # 공적분 강도 점수 (0~50점)
        score += (1 - pvalue) * 50
        
        # 정상성 보너스 (20점)
        if is_stationary:
            score += 20
        
        return score


if __name__ == "__main__":
    # 테스트
    from data_fetcher import BinanceDataFetcher
    
    fetcher = BinanceDataFetcher()
    tester = CointegrationTester()
    
    # 테스트 데이터
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
    data = fetcher.fetch_multiple_symbols(test_symbols, interval='4h', days=90)
    
    # 공적분 검정
    if len(data) >= 2:
        symbols = list(data.keys())
        price1 = data[symbols[0]]['close']
        price2 = data[symbols[1]]['close']
        
        result = tester.engle_granger_test(price1, price2)
        print(f"\n{symbols[0]} + {symbols[1]} 공적분 검정:")
        print(f"  p-value: {result['pvalue']:.4f}")
        print(f"  공적분 여부: {result['is_cointegrated']}")
        print(f"  강도: {result['strength']}")
