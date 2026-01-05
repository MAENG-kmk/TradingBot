"""
페어 트레이딩 포지션 정리 로직

페어로 진입한 포지션들을 다음 조건에서 정리:
1. Z-Score 회귀 (평균 회귀)
2. 손절/익절 조건
3. 페어 관계 깨짐
"""

import asyncio
import sys
import os
import numpy as np
from datetime import datetime

sys.path.append(os.path.abspath("."))
from MongoDB_python.client import addDataToMongoDB


def should_close_pair(position_info, symbol1, symbol2, client, getData):
    """
    페어 정리 조건 체크
    
    Args:
        position_info: 포지션 정보 딕셔너리
        symbol1, symbol2: 페어 심볼
        client: Binance client
        getData: get4HData 함수
    
    Returns:
        tuple: (should_close: bool, reason: str)
    """
    try:
        # 페어 정보 추출
        info1 = position_info.get(symbol1)
        info2 = position_info.get(symbol2)
        
        if not info1 or not info2:
            return True, "페어 정보 없음"
        
        # info 구조: [side, entry_zscore, 'pair', pair_symbol, hedge_ratio, base_symbol]
        entry_zscore = info1[1]
        hedge_ratio = info1[4]
        base_symbol = info1[5] if len(info1) > 5 else symbol1  # 하위 호환성
        
        # base_symbol이 symbol1인지 확인하여 순서 맞추기
        if base_symbol == symbol1:
            # 진입 시 순서와 동일
            data1 = getData(client, symbol1, 90)
            data2 = getData(client, symbol2, 90)
            price1 = data1['Close']
            price2 = data2['Close']
        else:
            # 순서가 반대인 경우 swap
            data1 = getData(client, symbol2, 90)
            data2 = getData(client, symbol1, 90)
            price1 = data1['Close']
            price2 = data2['Close']
        
        if len(data1) < 30 or len(data2) < 30:
            return False, "데이터 부족"
        
        # 현재 스프레드 계산 (진입 시와 동일한 순서)
        spread = price1 - hedge_ratio * price2
        spread_mean = spread.mean()
        spread_std = spread.std()
        
        if spread_std == 0 or np.isnan(spread_std):
            return True, "스프레드 표준편차 0"
        
        current_spread = spread.iloc[-1]
        current_zscore = (current_spread - spread_mean) / spread_std
        
        # 조건 1: Z-Score 평균 회귀 (진입 방향 반대로 돌아옴)
        if entry_zscore > 0:  # LONG_SPREAD로 진입 (zscore가 높아서)
            # zscore가 0.5 이하로 내려오면 정리
            if current_zscore < 0.5:
                return True, f"평균회귀 (Z: {entry_zscore:.2f} → {current_zscore:.2f})"
        else:  # SHORT_SPREAD로 진입 (zscore가 낮아서)
            # zscore가 -0.5 이상으로 올라오면 정리
            if current_zscore > -0.5:
                return True, f"평균회귀 (Z: {entry_zscore:.2f} → {current_zscore:.2f})"
        
        # 조건 2: Z-Score가 더 극단으로 갈 경우 (손절)
        # 진입 방향과 같은 방향으로 더 커지면 손절
        if entry_zscore > 0 and current_zscore > entry_zscore + 1.0:
            return True, f"손절 (Z: {entry_zscore:.2f} → {current_zscore:.2f})"
        if entry_zscore < 0 and current_zscore < entry_zscore - 1.0:
            return True, f"손절 (Z: {entry_zscore:.2f} → {current_zscore:.2f})"
        
        return False, "유지"
    
    except Exception as e:
        print(f"페어 정리 체크 에러: {e}")
        return False, "에러"


def closePositionPairTrading(client, createOrder, positions, position_info, 
                             getBalance, send_message, getData):
    """
    페어 트레이딩 포지션 정리
    
    Args:
        client: Binance client
        createOrder: 주문 생성 함수
        positions: 현재 포지션 목록
        position_info: 포지션 정보 딕셔너리
        getBalance: 잔고 조회 함수
        send_message: 텔레그램 메시지 함수
        getData: get4HData 함수
    """
    
    print("\n페어 트레이딩 포지션 정리 체크")
    
    # 처리된 페어를 추적 (중복 처리 방지)
    processed_pairs = set()
    datas = []
    
    for position in positions:
        symbol = position['symbol']
        
        # 이미 처리된 페어는 스킵
        if symbol in processed_pairs:
            continue
        
        # 포지션 정보가 없으면 기존 로직으로 처리
        if symbol not in position_info:
            print(f"⚠️  {symbol}: 페어 정보 없음 (기존 로직 필요)")
            continue
        
        info = position_info[symbol]
        
        # 페어 포지션이 아니면 스킵
        if len(info) < 4 or info[2] != 'pair':
            print(f"⚠️  {symbol}: 페어 포지션 아님")
            continue
        
        # 페어 심볼 추출
        pair_symbol = info[3]
        
        # 페어 상대가 포지션에 있는지 확인
        pair_position = None
        for p in positions:
            if p['symbol'] == pair_symbol:
                pair_position = p
                break
        
        if not pair_position:
            print(f"⚠️  {symbol}: 페어 상대 {pair_symbol} 포지션 없음")
            # 단독으로 정리
            close_single_position(client, createOrder, position, position_info, 
                                 datas, getBalance, "페어 상대 없음")
            processed_pairs.add(symbol)
            continue
        
        # 페어 정리 조건 체크
        should_close, reason = should_close_pair(
            position_info, symbol, pair_symbol, client, getData
        )
        
        if should_close:
            print(f"\n🔴 페어 정리: {symbol} + {pair_symbol}")
            print(f"   사유: {reason}")
            
            # 양쪽 포지션 모두 정리
            success1 = close_single_position(client, createOrder, position, 
                                           position_info, datas, getBalance, reason)
            success2 = close_single_position(client, createOrder, pair_position, 
                                           position_info, datas, getBalance, reason)
            
            if success1 and success2:
                print(f"✅ 페어 정리 완료")
            else:
                print(f"⚠️  페어 정리 일부 실패")
            
            # 처리됨 표시
            processed_pairs.add(symbol)
            processed_pairs.add(pair_symbol)
        else:
            print(f"⏭️  {symbol}+{pair_symbol}: {reason}")
    
    # MongoDB 저장
    if datas:
        addDataToMongoDB(datas)
        print(f"\n📊 {len(datas)}개 포지션 정리 데이터 저장")


def close_single_position(client, createOrder, position, position_info, 
                         datas, getBalance, reason):
    """
    단일 포지션 정리
    
    Args:
        client: Binance client
        createOrder: 주문 생성 함수
        position: 포지션 정보
        position_info: 포지션 정보 딕셔너리
        datas: 데이터 저장용 리스트
        getBalance: 잔고 조회 함수
        reason: 정리 사유
    
    Returns:
        bool: 성공 여부
    """
    symbol = position['symbol']
    
    try:
        # 청산 주문
        if position['side'] == 'long':
            response = createOrder(client, symbol, 'SELL', 'MARKET', position['amount'])
        else:
            response = createOrder(client, symbol, 'BUY', 'MARKET', position['amount'])
        
        if response:
            # 데이터 저장
            data = position.copy()
            data['closeTime'] = int(datetime.now().timestamp())
            data['closeReason'] = reason
            balance, _ = getBalance(client)
            data['balance'] = balance
            datas.append(data)
            
            # 포지션 정보 제거
            if symbol in position_info:
                position_info.pop(symbol)
            
            print(f"   {symbol}: {position['side']} {position['amount']} 정리 완료 "
                  f"(ROR: {position['ror']:.2f}%)")
            
            return True
        else:
            print(f"   ❌ {symbol} 주문 실패")
            return False
    
    except Exception as e:
        print(f"   ❌ {symbol} 정리 에러: {e}")
        return False


# main.py 호환 래퍼
def closePosition(client, createOrder, positions, position_info, 
                 getBalance, send_message, betController, getData=None):
    """
    포지션 정리 (main.py와 호환)
    
    페어 트레이딩용 closePosition
    getData 파라미터를 추가로 받아야 함
    """
    
    if getData is None:
        print("⚠️  getData 함수가 필요합니다 (get4HData)")
        return
    
    closePositionPairTrading(
        client=client,
        createOrder=createOrder,
        positions=positions,
        position_info=position_info,
        getBalance=getBalance,
        send_message=send_message,
        getData=getData
    )
