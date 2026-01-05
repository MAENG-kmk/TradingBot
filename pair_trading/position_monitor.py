"""
포지션 모니터링 및 청산 신호 관리

진입한 포지션의 청산 시점을 자동으로 감지합니다.
"""

import json
import time
from datetime import datetime, timedelta
import pandas as pd

from data_fetcher import BinanceDataFetcher
from cointegration_test import CointegrationTester


class PositionMonitor:
    """포지션 모니터링 및 청산 관리"""
    
    def __init__(self, positions_file='active_positions.json'):
        """
        초기화
        
        Args:
            positions_file: 활성 포지션 정보 파일
        """
        self.fetcher = BinanceDataFetcher()
        self.tester = CointegrationTester()
        self.positions_file = positions_file
        self.positions = self.load_positions()
    
    def load_positions(self):
        """활성 포지션 로드"""
        try:
            with open(self.positions_file, 'r') as f:
                data = json.load(f)
                return data.get('positions', [])
        except FileNotFoundError:
            return []
    
    def save_positions(self):
        """활성 포지션 저장"""
        with open(self.positions_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'positions': self.positions
            }, f, indent=2)
    
    def add_position(
        self,
        symbol1,
        symbol2,
        position_type,  # 'LONG_SPREAD' or 'SHORT_SPREAD'
        entry_zscore,
        entry_spread,
        hedge_ratio,
        entry_price1,
        entry_price2,
        position_size
    ):
        """
        새 포지션 추가
        
        Args:
            symbol1, symbol2: 코인 심볼
            position_type: 포지션 타입
            entry_zscore: 진입 Z-Score
            entry_spread: 진입 스프레드
            hedge_ratio: 헤징 비율
            entry_price1, entry_price2: 진입 가격
            position_size: 포지션 크기 (달러)
        """
        position = {
            'id': f"{symbol1}_{symbol2}_{int(time.time())}",
            'symbol1': symbol1,
            'symbol2': symbol2,
            'position_type': position_type,
            'entry_time': datetime.now().isoformat(),
            'entry_zscore': entry_zscore,
            'entry_spread': entry_spread,
            'hedge_ratio': hedge_ratio,
            'entry_price1': entry_price1,
            'entry_price2': entry_price2,
            'position_size': position_size,
            'status': 'ACTIVE'
        }
        
        self.positions.append(position)
        self.save_positions()
        
        print(f"\n✅ 포지션 추가: {symbol1} + {symbol2}")
        print(f"   타입: {position_type}")
        print(f"   진입 Z-Score: {entry_zscore:.2f}")
        print(f"   포지션 크기: ${position_size}")
    
    def check_exit_signals(self, position):
        """
        청산 신호 확인
        
        Returns:
            dict: 청산 신호 정보 또는 None
        """
        symbol1 = position['symbol1']
        symbol2 = position['symbol2']
        hedge_ratio = position['hedge_ratio']
        entry_time = datetime.fromisoformat(position['entry_time'])
        
        # 최신 데이터 가져오기
        data1 = self.fetcher.get_historical_klines(symbol1, interval='4h', days=90)
        data2 = self.fetcher.get_historical_klines(symbol2, interval='4h', days=90)
        
        if data1 is None or data2 is None:
            return None
        
        # 같은 인덱스
        common_index = data1.index.intersection(data2.index)
        price1 = data1.loc[common_index]['close']
        price2 = data2.loc[common_index]['close']
        
        # 현재 가격
        current_price1 = price1.iloc[-1]
        current_price2 = price2.iloc[-1]
        
        # 스프레드 계산
        spread = price1 - hedge_ratio * price2
        spread_mean = spread.tail(90).mean()
        spread_std = spread.tail(90).std()
        current_spread = spread.iloc[-1]
        zscore = (current_spread - spread_mean) / spread_std
        
        # 상관관계 (최근 30일)
        correlation = self.tester.calculate_correlation(
            price1.tail(180),
            price2.tail(180)
        )
        
        # 손익 계산
        pnl = self.calculate_pnl(
            position,
            current_price1,
            current_price2
        )
        
        pnl_pct = pnl / position['position_size']
        
        # 보유 시간
        holding_hours = (datetime.now() - entry_time).total_seconds() / 3600
        
        # 청산 신호 체크
        exit_signal = None
        
        # 1. 긴급 청산: 상관관계 붕괴
        if correlation < 0.70:
            exit_signal = {
                'type': 'EMERGENCY',
                'reason': f'상관관계 붕괴 ({correlation:.3f})',
                'priority': 1,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # 2. 손절매: 손실 한계 또는 역방향
        elif pnl_pct < -0.01:  # -1% 손실
            exit_signal = {
                'type': 'STOP_LOSS',
                'reason': f'손실 한계 ({pnl_pct*100:.2f}%)',
                'priority': 2,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # Z-Score 역방향 진행
        elif self._is_zscore_reversing(position, zscore):
            exit_signal = {
                'type': 'STOP_LOSS',
                'reason': f'Z-Score 역방향 ({zscore:.2f})',
                'priority': 2,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # 3. 수익 실현: 평균 복귀
        elif abs(zscore) < 0.5:
            exit_signal = {
                'type': 'TAKE_PROFIT',
                'reason': f'평균 복귀 (Z={zscore:.2f})',
                'priority': 3,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # 목표 수익 달성
        elif pnl_pct > 0.015:  # +1.5% 수익
            exit_signal = {
                'type': 'TAKE_PROFIT',
                'reason': f'목표 수익 ({pnl_pct*100:.2f}%)',
                'priority': 3,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # 4. 타임 스탑: 시간 초과
        elif holding_hours > 24 and pnl_pct > 0:
            exit_signal = {
                'type': 'TIME_STOP',
                'reason': f'시간 제한 ({holding_hours:.1f}h)',
                'priority': 4,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        # 강제 타임 스탑 (48시간)
        elif holding_hours > 48:
            exit_signal = {
                'type': 'TIME_STOP',
                'reason': f'강제 청산 ({holding_hours:.1f}h)',
                'priority': 4,
                'current_zscore': zscore,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'holding_hours': holding_hours
            }
        
        return exit_signal
    
    def _is_zscore_reversing(self, position, current_zscore):
        """Z-Score 역방향 진행 확인"""
        entry_zscore = position['entry_zscore']
        position_type = position['position_type']
        
        if position_type == 'LONG_SPREAD':
            # 롱 스프레드: Z-Score가 감소해야 함 (평균으로)
            # 역방향: Z-Score가 증가 (더 확대)
            return current_zscore > entry_zscore + 1.0
        
        elif position_type == 'SHORT_SPREAD':
            # 숏 스프레드: Z-Score가 증가해야 함 (평균으로)
            # 역방향: Z-Score가 감소 (더 축소)
            return current_zscore < entry_zscore - 1.0
        
        return False
    
    def calculate_pnl(self, position, current_price1, current_price2):
        """
        손익 계산
        
        Returns:
            float: 손익 (달러)
        """
        entry_price1 = position['entry_price1']
        entry_price2 = position['entry_price2']
        position_size = position['position_size']
        position_type = position['position_type']
        
        # 각 코인의 손익
        if position_type == 'LONG_SPREAD':
            # Coin1 롱, Coin2 숏
            pnl1 = (current_price1 - entry_price1) / entry_price1 * (position_size / 2)
            pnl2 = (entry_price2 - current_price2) / entry_price2 * (position_size / 2)
        
        elif position_type == 'SHORT_SPREAD':
            # Coin1 숏, Coin2 롱
            pnl1 = (entry_price1 - current_price1) / entry_price1 * (position_size / 2)
            pnl2 = (current_price2 - entry_price2) / entry_price2 * (position_size / 2)
        
        else:
            return 0
        
        return pnl1 + pnl2
    
    def monitor_all_positions(self):
        """모든 활성 포지션 모니터링"""
        
        if len(self.positions) == 0:
            print("\n활성 포지션 없음")
            return []
        
        print("\n" + "=" * 90)
        print(f"포지션 모니터링 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        
        exit_signals = []
        
        for i, position in enumerate(self.positions, 1):
            if position['status'] != 'ACTIVE':
                continue
            
            print(f"\n[{i}] {position['symbol1']} + {position['symbol2']}")
            print("-" * 90)
            
            # 진입 정보
            entry_time = datetime.fromisoformat(position['entry_time'])
            holding_hours = (datetime.now() - entry_time).total_seconds() / 3600
            
            print(f"진입 시간: {entry_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"보유 시간: {holding_hours:.1f}시간")
            print(f"포지션 타입: {position['position_type']}")
            print(f"진입 Z-Score: {position['entry_zscore']:.2f}")
            
            # 청산 신호 확인
            exit_signal = self.check_exit_signals(position)
            
            if exit_signal:
                exit_signal['position_id'] = position['id']
                exit_signal['position'] = position
                exit_signals.append(exit_signal)
                
                # 출력
                self._print_exit_signal(exit_signal)
            else:
                print("\n🟢 유지 (청산 신호 없음)")
            
            time.sleep(0.2)
        
        # 요약
        if exit_signals:
            self._print_exit_summary(exit_signals)
        
        return exit_signals
    
    def _print_exit_signal(self, signal):
        """청산 신호 출력"""
        
        icon_map = {
            'EMERGENCY': '🚨',
            'STOP_LOSS': '❌',
            'TAKE_PROFIT': '✅',
            'TIME_STOP': '⏰'
        }
        
        icon = icon_map.get(signal['type'], '⚪')
        
        print(f"\n{icon} 청산 신호: {signal['type']}")
        print(f"   이유: {signal['reason']}")
        print(f"   현재 Z-Score: {signal['current_zscore']:.2f}")
        print(f"   손익: ${signal['pnl']:.2f} ({signal['pnl_pct']*100:.2f}%)")
        print(f"   보유 시간: {signal['holding_hours']:.1f}시간")
        
        if signal['type'] == 'EMERGENCY':
            print("\n   ⚠️ 즉시 청산 권장!")
        elif signal['type'] == 'STOP_LOSS':
            print("\n   ⚠️ 손절매 실행 권장")
        elif signal['type'] == 'TAKE_PROFIT':
            print("\n   ✓ 수익 실현 가능")
    
    def _print_exit_summary(self, signals):
        """청산 신호 요약"""
        
        print("\n\n" + "=" * 90)
        print("청산 신호 요약")
        print("=" * 90)
        
        # 유형별 분류
        by_type = {}
        for sig in signals:
            sig_type = sig['type']
            by_type[sig_type] = by_type.get(sig_type, 0) + 1
        
        print(f"\n총 {len(signals)}개 청산 신호:")
        for sig_type, count in sorted(by_type.items()):
            print(f"  {sig_type}: {count}개")
        
        # 긴급/손절 우선 표시
        emergency = [s for s in signals if s['type'] == 'EMERGENCY']
        stop_loss = [s for s in signals if s['type'] == 'STOP_LOSS']
        
        if emergency:
            print(f"\n🚨 긴급 청산 필요: {len(emergency)}개")
            for sig in emergency:
                pos = sig['position']
                print(f"   {pos['symbol1']} + {pos['symbol2']}: {sig['reason']}")
        
        if stop_loss:
            print(f"\n❌ 손절매 권장: {len(stop_loss)}개")
            for sig in stop_loss:
                pos = sig['position']
                print(f"   {pos['symbol1']} + {pos['symbol2']}: {sig['reason']}")
    
    def close_position(self, position_id, reason=None):
        """포지션 청산 (기록만)"""
        
        for position in self.positions:
            if position['id'] == position_id:
                position['status'] = 'CLOSED'
                position['close_time'] = datetime.now().isoformat()
                position['close_reason'] = reason
                
                self.save_positions()
                
                print(f"\n✓ 포지션 청산: {position['symbol1']} + {position['symbol2']}")
                if reason:
                    print(f"  이유: {reason}")
                
                return True
        
        return False


def main():
    """메인 함수"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='포지션 모니터링')
    parser.add_argument('--continuous', action='store_true',
                       help='지속적 모니터링 (4시간마다)')
    
    args = parser.parse_args()
    
    monitor = PositionMonitor()
    
    if args.continuous:
        print("지속 모니터링 시작 (4시간 간격)")
        print("Ctrl+C로 중지\n")
        
        try:
            while True:
                signals = monitor.monitor_all_positions()
                
                # 다음 체크
                print(f"\n다음 체크: 4시간 후")
                time.sleep(4 * 3600)
        
        except KeyboardInterrupt:
            print("\n\n모니터링 중지")
    
    else:
        # 1회 체크
        signals = monitor.monitor_all_positions()
        
        # 청산 신호 JSON 저장
        if signals:
            with open('exit_signals.json', 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'signals': signals
                }, f, indent=2, default=str)
            
            print(f"\n✓ 청산 신호 저장: exit_signals.json")


if __name__ == "__main__":
    main()
