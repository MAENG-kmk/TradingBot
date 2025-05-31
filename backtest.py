import backtrader as bt
import pandas as pd
from datetime import datetime
import numpy as np

from backtestStrategy.SMACross import SMACross
from backtestStrategy.BolingerBend import BolingerBend
from backtestStrategy.LinearRegression import LinearRegressionStrategy
from backtestStrategy.TurtleStrategy import TurtleStrategy

# Cerebro 엔진 생성
cerebro = bt.Cerebro()
cerebro.addstrategy(TurtleStrategy)

# 데이터 로딩
dataName = 'btcusdt_4h'
data = bt.feeds.GenericCSVData(
    dataname='backtestDatas/' + dataName + '.csv',
    dtformat='%Y-%m-%d %H:%M:%S',
    timeframe=bt.TimeFrame.Minutes,
    compression=240,
    openinterest=-1,
    headers=True
)
cerebro.adddata(data)

# 초기 자본 설정
cerebro.broker.setcash(100000.0)

# 수수료 설정
cerebro.broker.setcommission(commission=0.0005)

# 백테스트 실행
# Print out the starting conditions
print('Data: {}'.format(dataName))
startBalance = cerebro.broker.getvalue()
print('Starting Portfolio Value: %.2f' % startBalance)
# Run over everything
cerebro.run()

# Print out the final result
finalBalance = cerebro.broker.getvalue()
print('Final Portfolio Value: %.2f' % finalBalance)

print('RoR: {:.2f}%'.format((finalBalance / startBalance - 1) * 100))

cerebro.plot()
