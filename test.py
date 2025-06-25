from binance.client import Client
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET
client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

from tools.getData import getData
from tools.getRsi import getRsi
from tools.getData import getData, getUsaTimeData, get1HData, get4HData
from tools.getTicker import getTicker
from tools.getBalance import getBalance
from tools.getMa import getMa, getMa_diff, getMACD
from tools.getVolume import getVolume
from tools.getPositions import getPositions
from tools.setLeverage import setLeverage
from tools.createOrder import createOrder
from tools.BetController import BetController
from tools.BetControllerTurtle import BetControllerTurtle
from logics.decidePosition import decidePosition
from logics.enterPosition import enterPosition
from tools.getLarry import getLarry
from tools.getBolinger import getBolinger
from tools.linearRegression import linearRegression
from tools.getAtr import getATR
from tools.checkRisk import checkRisk

import math
from datetime import datetime
from MongoDB_python.client import addDataToMongoDB, addVersionAndDate

############# enterPosition test ##################
ticker = getTicker(client)
# total_balance, available_balance = getBalance(client)
# positions = getPositions(client)
# position_info = {}
# logic_list = [getLarry, getMACD]
# betController = BetController(client)
# enterPosition(client, ticker, total_balance, available_balance, positions, position_info, logic_list, getUsaTimeData, getVolume, setLeverage, createOrder, betController)
####################################################

client.futures_create_order(
  symbol='BCHUSDT',
  side='SELL',
  type='LIMIT',
  quantity=0.045,
  timeInForce='GTX',
  price='482'
)
  