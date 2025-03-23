from binance.client import Client
client = Client(api_key="w6wGRNsx88wZHGNi6j2j663hyvEpDNHrLE6E6UntucPkJ4Lqp8P4rasX1lAx9ylE",
                api_secret="EtbkzmsRjVw2NHqis4rLlIvrZN4HVfHp77Qdzd8wG1AbyoXttLV8EgS7z9Efz9ut")

from tools.getData import getData
from tools.getRsi import getRsi
from tools.getData import getData, getUsaTimeData
from tools.getTicker import getTicker
from tools.getBalance import getBalance
from tools.getMa import getMa, getMa_diff, getMACD
from tools.getVolume import getVolume
from tools.getPositions import getPositions
from tools.setLeverage import setLeverage
from tools.createOrder import createOrder
from tools.BetController import BetController
from logics.decidePosition import decidePosition
from logics.enterPosition import enterPosition
from tools.getLarry import getLarry

import math
from datetime import datetime

############# enterPosition test ##################
# ticker = getTicker(client)
# total_balance, available_balance = getBalance(client)
# positions = getPositions(client)
# position_info = {}
# logic_list = [getLarry, getMACD]
# betController = BetController(client)
# enterPosition(client, ticker, total_balance, available_balance, positions, position_info, logic_list, getUsaTimeData, getVolume, setLeverage, createOrder, betController)
####################################################
data = getUsaTimeData(client, 'BTCUSDT', 60)
ma = getMACD(data)
print(ma)