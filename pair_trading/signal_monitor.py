"""
실시간 진입 신호 모니터링

4시간마다 선택된 페어의 Z-Score를 계산하고 진입 신호를 확인합니다.
"""

import json
import time
from datetime import datetime
import pandas as pd
import numpy as np

from data_fetcher import BinanceDataFetcher
from cointegration_test import CointegrationTester


class SignalMonitor:
    """실시간 진입 신호 모니터링"""
    
    def __init__(self, pairs_file='pair_trading_results.json'):
        """
        초기화
        
        Args:
            pairs_file: 페어 정보가 담긴 JSON 파일
        """
        self.fetcher = BinanceDataFetcher()
        self.tester = CointegrationTester()
        
        # 페어 정보 로드
        with open(pairs_file, 'r') as f:
            data = json.load(f)
            self.pairs = data['pairs']
        
        print(f"모니터링 대상: {len(self.pairs)}개 페어")
    
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
            dict: 신호 정보
        """
        symbol1 = pair_info['symbol1']
        symbol2 = pair_info['symbol2']
        hedge_ratio = pair_info['hedge_ratio']
        
        # 최신 데이터 가져오기
        data1 = self.fetcher.get_historical_klines(symbol1, interval='4h', days=90)
        data2 = self.fetcher.get_historical_klines(symbol2, interval='4h', days=90)
        
        if data1 is None or data2 is None:
            return None
        
        # 같은 인덱스로 맞추기
        common_index = data1.index.intersection(data2.index)
        price1 = data1.loc[common_index]['close']
        price2 = data2.loc[common_index]['close']
        
        # 상관관계 재확인 (최근 30일)
        recent_correlation = self.tester.calculate_correlation(
            price1.tail(180),  # 30일 × 6 (4시간봉)
            price2.tail(180)
        )
        
        # Z-Score 계산
        spread_stats = self.calculate_spread_zscore(
            price1, price2, hedge_ratio
        )
        
        zscore = spread_stats['zscore']
        
        # 신호 판단
        signal = {
            'timestamp': datetime.now().isoformat(),
            'symbol1': symbol1,
            'symbol2': symbol2,
            'correlation': recent_correlation,
            'zscore': zscore,
            'spread': spread_stats['current_spread'],
            'spread_mean': spread_stats['spread_mean'],
            'spread_std': spread_stats['spread_std'],
            'hedge_ratio': hedge_ratio,
            'signal': 'WAIT',
            'action': None,
            'reason': None
        }
        
        # 상관관계 체크
        if recent_correlation < min_correlation:
            signal['signal'] = 'SKIP'
            signal['reason'] = f'상관관계 낮음 ({recent_correlation:.3f})'
            return signal
        
        # 진입 신호 확인
        if zscore > zscore_threshold:
            signal['signal'] = 'ENTER'
            signal['action'] = 'LONG_SPREAD'
            signal['reason'] = f'스프레드 과대 확대 (Z={zscore:.2f})'
            signal['position'] = {
                'symbol1_side': 'LONG',
                'symbol2_side': 'SHORT',
                'description': f'{symbol1} 롱 + {symbol2} 숏'
            }
        
        elif zscore < -zscore_threshold:
            signal['signal'] = 'ENTER'
            signal['action'] = 'SHORT_SPREAD'
            signal['reason'] = f'스프레드 과도 축소 (Z={zscore:.2f})'
            signal['position'] = {
                'symbol1_side': 'SHORT',
                'symbol2_side': 'LONG',
                'description': f'{symbol1} 숏 + {symbol2} 롱'
            }
        
        elif abs(zscore) > zscore_threshold * 0.8:  # 80% 지점
            signal['signal'] = 'WATCH'
            signal['reason'] = f'진입 임박 (Z={zscore:.2f})'
        
        else:
            signal['signal'] = 'WAIT'
            signal['reason'] = f'평균 근처 (Z={zscore:.2f})'
        
        return signal
    
    def monitor_all_pairs(self):
        """모든 페어 모니터링"""
        
        print("\n" + "=" * 90)
        print(f"페어 트레이딩 신호 모니터링 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        
        signals = []
        
        for i, pair in enumerate(self.pairs, 1):
            print(f"\n[{i}/{len(self.pairs)}] {pair['symbol1']} + {pair['symbol2']}")
            print("-" * 90)
            
            signal = self.check_entry_signal(pair)
            
            if signal is None:
                print("❌ 데이터 조회 실패")
                continue
            
            signals.append(signal)
            
            # 결과 출력
            self._print_signal(signal)
            
            # API rate limit
            time.sleep(0.2)
        
        # 요약
        self._print_summary(signals)
        
        return signals
    
    def _print_signal(self, signal):
        """신호 출력"""
        
        print(f"상관관계: {signal['correlation']:.4f}")
        print(f"Z-Score: {signal['zscore']:.2f}")
        print(f"스프레드: {signal['spread']:.2f} "
              f"(평균: {signal['spread_mean']:.2f}, "
              f"표준편차: {signal['spread_std']:.2f})")
        
        # 신호별 색상 아이콘
        signal_icons = {
            'ENTER': '🔴',
            'WATCH': '🟡',
            'WAIT': '🟢',
            'SKIP': '⚫'
        }
        
        icon = signal_icons.get(signal['signal'], '⚪')
        print(f"\n{icon} 신호: {signal['signal']}")
        print(f"   {signal['reason']}")
        
        if signal['action']:
            print(f"\n✅ 진입 조치:")
            print(f"   전략: {signal['action']}")
            print(f"   포지션: {signal['position']['description']}")
            print(f"   {signal['symbol1']}: {signal['position']['symbol1_side']}")
            print(f"   {signal['symbol2']}: {signal['position']['symbol2_side']}")
    
    def _print_summary(self, signals):
        """요약 출력"""
        
        print("\n\n" + "=" * 90)
        print("요약")
        print("=" * 90)
        
        # 신호별 카운트
        signal_count = {}
        for s in signals:
            signal_type = s['signal']
            signal_count[signal_type] = signal_count.get(signal_type, 0) + 1
        
        print(f"\n총 {len(signals)}개 페어:")
        for signal_type, count in sorted(signal_count.items()):
            print(f"  {signal_type}: {count}개")
        
        # 진입 신호만 따로 출력
        entry_signals = [s for s in signals if s['signal'] == 'ENTER']
        
        if entry_signals:
            print(f"\n🔴 진입 신호 발생: {len(entry_signals)}개")
            print("-" * 90)
            
            for sig in entry_signals:
                print(f"\n{sig['symbol1']} + {sig['symbol2']}")
                print(f"  Z-Score: {sig['zscore']:.2f}")
                print(f"  전략: {sig['action']}")
                print(f"  포지션: {sig['position']['description']}")
        else:
            print("\n🟢 현재 진입 신호 없음")
    
    def run_continuous(self, interval_hours=4):
        """
        지속적 모니터링 (4시간마다)
        
        Args:
            interval_hours: 체크 간격 (시간)
        """
        print(f"지속 모니터링 시작 ({interval_hours}시간 간격)")
        print("Ctrl+C로 중지")
        
        try:
            while True:
                signals = self.monitor_all_pairs()
                
                # 다음 체크 시간
                next_check = datetime.now()
                next_check = next_check.replace(
                    hour=(next_check.hour // interval_hours + 1) * interval_hours % 24,
                    minute=0,
                    second=0
                )
                
                print(f"\n다음 체크: {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 대기
                wait_seconds = (next_check - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
        
        except KeyboardInterrupt:
            print("\n\n모니터링 중지")


def main():
    """메인 함수"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='페어 트레이딩 신호 모니터링')
    parser.add_argument('--continuous', action='store_true', 
                       help='지속적 모니터링 (4시간마다)')
    parser.add_argument('--threshold', type=float, default=2.5,
                       help='Z-Score 임계값 (기본: 2.5)')
    
    args = parser.parse_args()
    
    # 모니터 생성
    monitor = SignalMonitor('pair_trading_results.json')
    
    if args.continuous:
        # 지속 모니터링
        monitor.run_continuous(interval_hours=4)
    else:
        # 1회 체크
        signals = monitor.monitor_all_pairs()
        
        # 진입 신호 있으면 JSON 저장
        entry_signals = [s for s in signals if s['signal'] == 'ENTER']
        if entry_signals:
            with open('entry_signals.json', 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'signals': entry_signals
                }, f, indent=2)
            print(f"\n✓ 진입 신호 저장: entry_signals.json")


if __name__ == "__main__":
    main()
