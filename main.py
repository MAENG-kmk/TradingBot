"""
10개 코인 맞춤형 자동매매

대상: ETH, BTC, SOL, BNB, XRP, LINK, DOGE, AVAX, ARB, AAVE
각 코인 strategy.py가 진입/청산을 자체 관리.

사용법:
  python main.py
"""
from binance.client import Client
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

from tools.getBalance import getBalance
from tools.getPositions import getPositions
from tools.telegram import send_message
from MongoDB_python.client import addVersionAndDate
from coins import STRATEGY_CLASSES

import asyncio
import time

# 초기화
balance, available = getBalance(client)
addVersionAndDate(COLLECTION, balance)

# 코인별 전략 인스턴스
strategies = [cls(client) for cls in STRATEGY_CLASSES]

print("=" * 50)
print("10코인 맞춤형 자동매매 시작")
print(f"대상: {', '.join(s.SYMBOL for s in strategies)}")
print(f"잔고: ${float(balance):,.2f}")
print("=" * 50)


def run_trading_bot():
    while True:
        try:
            for strategy in strategies:
              positions = getPositions(client)
              total_balance, available_balance = getBalance(client)
              strategy.run(positions, total_balance, available_balance)

            time.sleep(300)

        except Exception as e:
            print(f"❌ 오류: {e}")
            asyncio.run(send_message(f"Error: {e}"))
            time.sleep(60)


run_trading_bot()
