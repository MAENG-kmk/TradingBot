"""
최적 페어 찾기 메인 모듈
"""

import pandas as pd
from datetime import datetime
import json
import os

from data_fetcher import BinanceDataFetcher
from cointegration_test import CointegrationTester


class PairFinder:
    """최적 페어 트레이딩 쌍 찾기"""
    
    def __init__(self, api_key=None, api_secret=None):
        """
        초기화
        
        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret
        """
        self.fetcher = BinanceDataFetcher(api_key, api_secret)
        self.tester = CointegrationTester(significance_level=0.05)
        self.results = None
    
    def find_best_pairs(
        self,
        top_n=5,
        max_symbols=30,
        interval='4h',
        days=90,
        min_volume=50000000,
        min_correlation=0.70
    ):
        """
        최적 페어 찾기
        
        Args:
            top_n: 상위 N개 쌍 반환
            max_symbols: 최대 검사할 심볼 수
            interval: 시간 간격 (1h, 4h, 1d)
            days: 과거 데이터 일수
            min_volume: 최소 24시간 거래량 (USD)
            min_correlation: 최소 상관계수
        
        Returns:
            list: 상위 N개 페어 정보
        """
        print("=" * 80)
        print("Binance Futures 페어 트레이딩 최적 쌍 찾기")
        print("=" * 80)
        
        # Step 1: 심볼 조회
        print(f"\n[Step 1] 거래 가능한 심볼 조회")
        print("-" * 80)
        symbols = self.fetcher.get_futures_symbols(
            quote_asset='USDT',
            min_volume=min_volume
        )
        print(f"총 {len(symbols)}개 심볼 발견")
        
        # 상위 N개만 선택
        symbols = symbols[:max_symbols]
        print(f"상위 {len(symbols)}개 선택 (거래량 기준)")
        
        # Step 2: 데이터 수집
        print(f"\n[Step 2] 과거 데이터 수집 ({interval}, {days}일)")
        print("-" * 80)
        price_data = self.fetcher.fetch_multiple_symbols(
            symbols,
            interval=interval,
            days=days
        )
        
        if len(price_data) < 2:
            print("❌ 데이터 부족 (최소 2개 필요)")
            return []
        
        print(f"데이터 수집 완료: {len(price_data)}개")
        
        # Step 3: 공적분 검정
        print(f"\n[Step 3] 공적분 검정 (최소 상관계수: {min_correlation})")
        print("-" * 80)
        cointegrated_pairs = self.tester.find_cointegrated_pairs(
            price_data,
            min_correlation=min_correlation
        )
        
        if len(cointegrated_pairs) == 0:
            print("❌ 공적분 쌍을 찾지 못했습니다")
            return []
        
        # Step 4: 상위 N개 선택
        print(f"\n[Step 4] 상위 {top_n}개 쌍 선택")
        print("-" * 80)
        
        top_pairs = cointegrated_pairs[:top_n]
        self.results = top_pairs
        
        # 결과 출력
        self._print_results(top_pairs)
        
        return top_pairs
    
    def _print_results(self, pairs):
        """결과 출력"""
        print("\n" + "=" * 80)
        print("최적 페어 트레이딩 쌍")
        print("=" * 80)
        
        for i, pair in enumerate(pairs, 1):
            print(f"\n{i}. {pair['symbol1']} + {pair['symbol2']}")
            print(f"   ├─ 상관계수: {pair['correlation']:.4f}")
            print(f"   ├─ 공적분 p-value: {pair['pvalue']:.4f} ({pair['strength']})")
            print(f"   ├─ 헤징 비율: {pair['hedge_ratio']:.4f}")
            print(f"   ├─ 현재 Z-Score: {pair['current_zscore']:.2f}")
            print(f"   ├─ 스프레드 정상성: {'✓' if pair['is_stationary'] else '✗'}")
            print(f"   └─ 종합 점수: {pair['score']:.2f}/100")
            
            # 거래 추천
            zscore = pair['current_zscore']
            if abs(zscore) > 2.5:
                signal = "진입 신호 강함" if zscore > 0 else "진입 신호 강함 (역방향)"
            elif abs(zscore) > 2.0:
                signal = "진입 고려"
            else:
                signal = "대기"
            print(f"      현재 상태: {signal}")
    
    def save_results(self, filename='pair_trading_results.json'):
        """
        결과를 JSON 파일로 저장
        
        Args:
            filename: 저장할 파일명
        """
        if self.results is None:
            print("저장할 결과가 없습니다")
            return
        
        # 현재 스크립트 위치
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(current_dir, filename)
        
        # 저장할 데이터 준비
        save_data = {
            'timestamp': datetime.now().isoformat(),
            'pairs': []
        }
        
        for pair in self.results:
            save_data['pairs'].append({
                'symbol1': pair['symbol1'],
                'symbol2': pair['symbol2'],
                'correlation': float(pair['correlation']),
                'pvalue': float(pair['pvalue']),
                'strength': pair['strength'],
                'hedge_ratio': float(pair['hedge_ratio']),
                'current_zscore': float(pair['current_zscore']),
                'is_stationary': bool(pair['is_stationary']),
                'adf_pvalue': float(pair['adf_pvalue']),
                'score': float(pair['score'])
            })
        
        # JSON 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 결과 저장: {filepath}")
    
    def generate_report(self, filename='pair_trading_report.md'):
        """
        마크다운 리포트 생성
        
        Args:
            filename: 저장할 파일명
        """
        if self.results is None:
            print("리포트 생성할 결과가 없습니다")
            return
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(current_dir, filename)
        
        # 리포트 작성
        report = []
        report.append("# Binance Futures 페어 트레이딩 최적 쌍")
        report.append(f"\n생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\n총 발견: {len(self.results)}개 쌍")
        report.append("\n---\n")
        
        for i, pair in enumerate(self.results, 1):
            report.append(f"## {i}. {pair['symbol1']} + {pair['symbol2']}")
            report.append("\n### 통계 지표")
            report.append(f"- **상관계수**: {pair['correlation']:.4f}")
            report.append(f"- **공적분 p-value**: {pair['pvalue']:.4f} ({pair['strength']})")
            report.append(f"- **헤징 비율**: {pair['hedge_ratio']:.4f}")
            report.append(f"- **현재 Z-Score**: {pair['current_zscore']:.2f}")
            report.append(f"- **스프레드 정상성**: {'✓ 정상' if pair['is_stationary'] else '✗ 비정상'}")
            report.append(f"- **종합 점수**: {pair['score']:.2f}/100")
            
            report.append("\n### 거래 설정")
            report.append(f"- **타임프레임**: 4시간")
            report.append(f"- **진입 신호**: Z-Score > 2.5 또는 < -2.5")
            report.append(f"- **청산 신호**: Z-Score < 0.5")
            report.append(f"- **포지션 비중**: {pair['symbol1']} 50% + {pair['symbol2']} 50% (달러값)")
            
            # 현재 상태
            zscore = pair['current_zscore']
            if abs(zscore) > 2.5:
                status = "🔴 진입 신호"
                action = f"{'롱 스프레드' if zscore > 0 else '숏 스프레드'} 진입 고려"
            elif abs(zscore) > 2.0:
                status = "🟡 주의 관찰"
                action = "진입 준비"
            else:
                status = "🟢 대기"
                action = "신호 대기 중"
            
            report.append(f"\n### 현재 상태")
            report.append(f"- **상태**: {status}")
            report.append(f"- **권장 조치**: {action}")
            
            report.append("\n---\n")
        
        # 파일 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        
        print(f"✓ 리포트 저장: {filepath}")


def main():
    """메인 실행 함수"""
    
    # PairFinder 생성 (API 키 없이 public data 사용)
    finder = PairFinder()
    
    # 최적 쌍 찾기
    top_pairs = finder.find_best_pairs(
        top_n=5,              # 상위 5개
        max_symbols=30,       # 최대 30개 코인 검사
        interval='4h',        # 4시간 봉
        days=90,              # 90일 데이터
        min_volume=50000000,  # 최소 5천만 달러 거래량
        min_correlation=0.70  # 최소 상관계수 0.70
    )
    
    # 결과 저장
    if top_pairs:
        finder.save_results('pair_trading_results.json')
        finder.generate_report('pair_trading_report.md')
        
        print("\n" + "=" * 80)
        print("완료!")
        print("=" * 80)
        print("\n생성된 파일:")
        print("  - pair_trading_results.json (JSON 데이터)")
        print("  - pair_trading_report.md (마크다운 리포트)")
    else:
        print("\n❌ 적합한 쌍을 찾지 못했습니다")


if __name__ == "__main__":
    main()
