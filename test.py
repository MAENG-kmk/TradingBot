from binance.client import Client
client = Client(api_key="w6wGRNsx88wZHGNi6j2j663hyvEpDNHrLE6E6UntucPkJ4Lqp8P4rasX1lAx9ylE",
                api_secret="EtbkzmsRjVw2NHqis4rLlIvrZN4HVfHp77Qdzd8wG1AbyoXttLV8EgS7z9Efz9ut")

from tools.getData import getData
from tools.getRsi import getRsi
from tools.getData import getData, getUsaTimeData
from tools.getTicker import getTicker
from tools.getBalance import getBalance
from tools.getMa import getMa, getMa_diff
from tools.getVolume import getVolume
from logics.decidePosition import decidePosition
from tools.getLarry import getLarry

import math

data = getUsaTimeData(client, 'BTCUSDT', 20)
print(data)
# ma = getMa_diff(data)
# ticker = getTicker(client)
# BTC_data = getData(client, 'BTCUSDT', '1d', 30)
# side = decidePosition(ticker, BTC_data, getMa)

