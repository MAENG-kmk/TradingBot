"""
main.py 수정 가이드

페어 트레이딩 전략을 사용하도록 변경
"""

# 기존 import
from binance.client import Client
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)

from tools.BetController import BetController
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.getData import getData, get4HData
from tools.getTicker import getTicker
from tools.getPositions import getPositions
from tools.createOrder import createOrder
from tools.isPositionFull import isPositionFull
from tools.setLeverage import setLeverage
from tools.getBolinger import getBolinger
from tools.getMa import getMACD

# ✅ 새로 추가: 페어 트레이딩 import
from logics.enterPositionPairTrading import enterPositionPairTrading
from logics.closePosition import closePosition

from MongoDB_python.client import addVersionAndDate
import asyncio
import time

logic_list = [getBolinger, getMACD]

balance, available = getBalance(client)
betController = BetController(client, logic_list)
addVersionAndDate(COLLECTION, balance)


def run_trading_bot():
    """메인 트레이딩 봇 (페어 트레이딩 버전)"""
    
    position_info = {}
    winning_history = [0, 0, 0, 0]
    
    print("=" * 70)
    print("페어 트레이딩 봇 시작")
    print("=" * 70)
    
    while True:
        try:
            positions = getPositions(client)
            
            # 포지션이 있다면 정리할게 있는지 체크
            if len(positions) > 0:
                print("포지션 정리 체크 중,,,")
                closePosition(
                    client, createOrder, positions, position_info,
                    winning_history, getBalance, send_message, betController
                )
            
            # 포지션이 꽉 찼는지 체크
            total_balance, available_balance = getBalance(client)
            
            if not isPositionFull(total_balance, available_balance):
                print("페어 트레이딩 진입 체크 중,,,")
                
                # ✅ 페어 트레이딩 진입 (ticker 불필요)
                enterPositionPairTrading(
                    client=client,
                    total_balance=total_balance,
                    available_balance=available_balance,
                    positions=positions,
                    position_info=position_info,
                    setLeverage=setLeverage,
                    createOrder=createOrder,
                    betController=betController,
                    zscore_threshold=2.5  # Z-Score 임계값
                )
            
            # 대기 시간 (15초 유지 또는 조정)
            time.sleep(15)
        
        except Exception as e:
            print('Error:', e)
            asyncio.run(send_message(f"Error code: {e}"))


# 실행
if __name__ == "__main__":
    run_trading_bot()
