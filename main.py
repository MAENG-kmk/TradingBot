from binance.client import Client
client = Client(api_key="w6wGRNsx88wZHGNi6j2j663hyvEpDNHrLE6E6UntucPkJ4Lqp8P4rasX1lAx9ylE",
                api_secret="EtbkzmsRjVw2NHqis4rLlIvrZN4HVfHp77Qdzd8wG1AbyoXttLV8EgS7z9Efz9ut")

from tools.BetController import BetController
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.getData import getData, getUsaTimeData
from tools.getTicker import getTicker
from tools.getPositions import getPositions
from tools.createOrder import createOrder
from tools.isPositionFull import isPositionFull
from tools.setLeverage import setLeverage
from tools.getRsi import getRsi
from tools.getMa import getMa, getMa_diff, getMACD
from tools.getVolume import getVolume
from tools.getLarry import getLarry

from logics.decidePosition import decidePosition
from logics.closePosition import closePosition
from logics.enterPosition import enterPosition
import asyncio
import time


balance, available = getBalance(client)
betController = BetController(client)
asyncio.run(send_message('Start balance: {}$'.format(round(float(balance)*100)/100)))

logic_list = [getLarry, getMACD]

def run_trading_bot():
  position_info = {}
  winning_history = [0, 0, 0, 0]
  while True:
    try:
      positions = getPositions(client)
      # 포지션이 있다면 정리할게 있는지 체크
      if len(positions) > 0:
        print("포지션 정리 체크 중,,,")
        closePosition(client, createOrder, positions, position_info, winning_history, getBalance, send_message, betController)

      # 포지션이 꽉 찼는지 체크
      # 빈 포지션이 있다면 코인 찾기
      total_balance, available_balance = getBalance(client)
      
      if not isPositionFull(total_balance, available_balance):
        print("포지션 진입 체크 중,,,")
        ticker = getTicker(client)
        positions = getPositions(client)
        enterPosition(client, ticker, total_balance, available_balance, positions, position_info, logic_list, getUsaTimeData, getVolume, setLeverage, createOrder, betController)
        
      print("정상 작동 중,,,")
      time.sleep(60)
      
    except Exception as e:
      print(e)
      asyncio.run(send_message(f"Error code: {e}"))
  
run_trading_bot()
