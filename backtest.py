import backtrader as bt
import pandas as pd
from datetime import datetime
import numpy as np

from backtestStrategy.SMACross import SMACross
from backtestStrategy.BolingerBend import BolingerBend
from backtestStrategy.LinearRegression import LinearRegressionStrategy
from backtestStrategy.TurtleStrategy import TurtleStrategy
from backtestStrategy.OptimizedStrategy import OptimizedStrategy
from backtestStrategy.SDE_OnlyStrategy import SDE_OnlyStrategy
from backtestStrategy.LarryStrategy import LarryStrategy

# ===== 사용할 전략 선택 =====
STRATEGY = OptimizedStrategy  # OptimizedStrategy, LarryStrategy 등으로 변경 가능

# Cerebro 엔진 생성
cerebro = bt.Cerebro()
cerebro.addstrategy(STRATEGY)

# 데이터 로딩
dataName = 'ethusdt_4h'
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
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
print('Starting Portfolio Value: %.2f' % startBalance)
# Run over everything
result = cerebro.run()
strat = result[0]

# Print out the final result
finalBalance = cerebro.broker.getvalue()

# TradeAnalyzer 결과
trade_analysis = strat.analyzers.trades.get_analysis()
print('\n=== 거래 결과 ===')
total_trades = trade_analysis.total.total  # 총 거래 횟수
won_trades = trade_analysis.won.total      # 수익 거래
lost_trades = trade_analysis.lost.total    # 손실 거래
net_pnl = trade_analysis.pnl.net.total     # 총 손익 (수수료 포함)

# 평균 수익과 평균 손실
avg_profit = trade_analysis.won.pnl.average if won_trades > 0 else 0
avg_loss = trade_analysis.lost.pnl.average if lost_trades > 0 else 0

# ROR (Rate of Return) 계산
ror = (finalBalance - startBalance) / startBalance * 100

# Sharpe Ratio 계산
sharpe_analysis = strat.analyzers.sharpe.get_analysis()
sharpe_ratio = sharpe_analysis.get('sharperatio', None)

# Maximum Drawdown 계산
drawdown_analysis = strat.analyzers.drawdown.get_analysis()
max_drawdown = drawdown_analysis.get('max', {'drawdown': 0})['drawdown']

print(f'총 거래 횟수: {total_trades}')
print(f'수익 거래: {won_trades}')
print(f'손실 거래: {lost_trades}')
print(f'승률: {won_trades / total_trades * 100:.1f}%')
print(f'평균 수익: ${avg_profit:.2f}')
print(f'평균 손실: ${avg_loss:.2f}')
print(f'수익/손실 비율: {abs(avg_profit / avg_loss):.2f}' if avg_loss != 0 else '수익/손실 비율: N/A')
print(f'총 손익: ${net_pnl:.2f}')
print(f'ROR (수익률): {ror:.2f}%')
print(f'Sharpe Ratio: {sharpe_ratio:.2f}' if sharpe_ratio else 'Sharpe Ratio: N/A')
print(f'최대 낙폭 (MDD): {max_drawdown:.2f}%')
print(f'최종 자본: ${finalBalance:.2f}')


cerebro.plot()
