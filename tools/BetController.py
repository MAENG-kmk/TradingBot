from .getData import getUsaTimeData
from .getMa import getMa


class BetController:
  def __init__(self, client):
    self.client = client
    self.targetRorChecker = {}
    self.defaultTargetRor = 3
    self.defaultStopLoss = -2
    self.adjustRor = 1
    
  def saveNew(self, symbol):
    self.targetRorChecker[symbol] = [self.defaultTargetRor, self.defaultStopLoss]
    
  def bet(self, symbol, side):
    data = getUsaTimeData(self.client, symbol, 30)
    ma = getMa(data)
    currentSide = ma
    # if side == currentSide:
    if True:
      self.targetRorChecker[symbol] = [self.targetRorChecker[symbol][0]+self.adjustRor, self.targetRorChecker[symbol][0]-self.adjustRor]
      return 'bet'
    else:
      return 'close'
  
  def getClosePositions(self, positions):
    list_to_close = []
    for position in positions:
      symbol = position['symbol']
      ror = position['ror']
      if symbol not in self.targetRorChecker:
        self.saveNew(symbol)
      [targetRor, stopLoss] = self.targetRorChecker[symbol]
      if ror >= targetRor:
        betting = self.bet(symbol, position['side'])
        if betting == 'close':
          list_to_close.append(position)  
          self.targetRorChecker.pop(symbol, None)
      elif ror < stopLoss:
        list_to_close.append(position)
        self.targetRorChecker.pop(symbol, None)
        
    return list_to_close