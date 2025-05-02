from binance.client import Client
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

from tools.BetController import BetController
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.getData import getData, getUsaTimeData, get1HData
from tools.getTicker import getTicker
from tools.getPositions import getPositions
from tools.createOrder import createOrder
from tools.isPositionFull import isPositionFull
from tools.setLeverage import setLeverage
from tools.getRsi import getRsi
from tools.getMa import getMa, getMa_diff, getMACD
from tools.getVolume import getVolume
from tools.getLarry import getLarry
from tools.getBolinger import getBolinger

from logics.decidePosition import decidePosition
from logics.closePosition import closePosition
from logics.enterPosition import enterPosition

from MongoDB_python.client import addVersionAndDate
import asyncio
import time

logic_list = [getBolinger, getMACD]

balance, available = getBalance(client)
betController = BetController(client, logic_list)
# asyncio.run(send_message('Start balance: {}$'.format(round(float(balance)*100)/100)))
addVersionAndDate(COLLECTION, balance)


def run_trading_bot():
  position_info = {}
  special_care = {}
  winning_history = [0, 0, 0, 0]
  while True:
    try:
      positions = getPositions(client)
      # 포지션이 있다면 정리할게 있는지 체크
      if len(positions) > 0:
        # print("포지션 정리 체크 중,,,")
        closePosition(client, createOrder, positions, position_info, winning_history, getBalance, send_message, betController, special_care)

      # 포지션이 꽉 찼는지 체크
      # 빈 포지션이 있다면 코인 찾기
      total_balance, available_balance = getBalance(client)
      
      if not isPositionFull(total_balance, available_balance):
        # print("포지션 진입 체크 중,,,")
        ticker = getTicker(client)
        positions = getPositions(client)
        enterPosition(client, ticker, total_balance, available_balance, positions, position_info, logic_list, get1HData, getVolume, setLeverage, createOrder, betController, special_care)
        
      # print("정상 작동 중,,,")
      time.sleep(30)
      
    except Exception as e:
      print('e:', e)
      asyncio.run(send_message(f"Error code: {e}"))
  
run_trading_bot()
