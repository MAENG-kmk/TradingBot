from binance.client import Client
client = Client(api_key="w6wGRNsx88wZHGNi6j2j663hyvEpDNHrLE6E6UntucPkJ4Lqp8P4rasX1lAx9ylE",
                api_secret="EtbkzmsRjVw2NHqis4rLlIvrZN4HVfHp77Qdzd8wG1AbyoXttLV8EgS7z9Efz9ut")

from tools.getMa import getMa, getMACD
from tools.getData import getData
import matplotlib.pyplot as plt

class Backtest:
  def __init__(self, data):
    self.data = data
    print('데이터 수: {}'.format(len(data)))
    self.position = 'None'
    self.fee = 0.001
    self.ror = 1
    self.enterPrice = 0
    self.history = {
      'longWin': 0,
      'longLose': 0,
      'shortWin': 0,
      'shortLose': 0,
    }
    self.profits = []
    self.stopLoss = 0
    self.targetPrice = 0
    self.tp = 0.05
    self.sl = 0.02
    self.k = 0.5 
    
  def clear(self):
    self.stopLoss = 0
    self.targetPrice = 0
    self.position = 'None'
    self.enterPrice = 0
    
  def calculateRor(self, closePrice):
    if self.position == 'long':
      profit = closePrice / self.enterPrice - self.fee
    else:
      profit = 2 - closePrice / self.enterPrice - self.fee
    
    self.ror *= profit
    self.profits.append(profit-1)

    
  def enterLogic(self, i):
    data = self.data.iloc[i-30:i+1]
    ma = getMa(data.iloc[:-1])
    cur = data.iloc[-1]
    range = (data.iloc[-2]['High'] - data.iloc[-2]['Low']) * self.k
    if range < cur['Open'] * 0.009:
      return
    if ma == 'long':
      if cur['Open']+range < cur['High']:
        self.position = 'long'
        self.enterPrice = cur['Open'] + range
        self.stopLoss = self.enterPrice * (1 - self.sl)
        self.targetPrice = self.enterPrice * (1 + self.tp)
    else:
      if cur['Open']-range > cur['Low']:
        self.position = 'short'
        self.enterPrice = cur['Open'] - range
        self.stopLoss = self.enterPrice * (1 + self.sl)
        self.targetPrice = self.enterPrice * (1 - self.tp)

  
  def closeLogic(self, i):
    closePrice = self.data.iloc[i]['Open']
    if self.position == 'long':
      if closePrice > self.targetPrice:
        self.history['longWin'] += 1
        self.calculateRor(self.targetPrice)
        self.clear()
      elif closePrice < self.stopLoss:
        self.history['longLose'] += 1
        self.calculateRor(self.stopLoss)
        self.clear()
        
    else:
      if closePrice < self.targetPrice:
        self.history['shortWin'] += 1
        self.calculateRor(self.targetPrice)
        self.clear()
      elif closePrice > self.stopLoss:
        self.history['shortLose'] += 1
        self.calculateRor(self.stopLoss)
        self.clear()

      
  
  def excute(self):
    for i in range(30, len(self.data)):
      if self.position == 'None':
        enter = self.enterLogic(i)
      else:
        close = self.closeLogic(i)
        
  def result(self):
    print('수익률: {:.2f}%'.format((self.ror-1) * 100))
    print('롱 승리: {}, 롱 패배: {}, 승률: {:.2f}%'.format(self.history['longWin'], self.history['longLose'], self.history['longWin']/(self.history['longWin']+self.history['longLose'])*100))
    print('숏 승리: {}, 숏 패배: {}, 승률: {:.2f}%'.format(self.history['shortWin'], self.history['shortLose'], self.history['shortWin']/(self.history['shortWin']+self.history['shortLose'])*100))
    print('평균 수익률: {:.2f}%'.format(sum(self.profits)/len(self.profits)*100))
    print('MDD: {:.2f}%'.format(min(self.profits)*100))
    
  # def find_k(self):
  #   x = []
  #   y = []
  #   for k in range(30, 71):
  #     K = k/100
  #     self.k = K
  #     self.excute()
  #     x.append(K)
  #     y.append(self.ror)
  #     self.clear()
  #     self.ror = 1
  #     self.profits = []
  #   plt.plot(x, y)
  #   plt.xlabel("larry's K")
  #   plt.ylabel('ROR')
  #   plt.title('BTCUSDT 1500day backtest')
  #   plt.show()
    
    
    
data = getData(client, 'BTCUSDT', '1d', 1500)
backtest = Backtest(data)
backtest.excute()
backtest.result()
# backtest.find_k()