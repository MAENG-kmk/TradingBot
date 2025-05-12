from .getData import get4HData
from .getMa import getMa
from .getBolinger import getBolingerClose


class BetController:
  def __init__(self, client, logicList):
    self.client = client
    self.targetRorChecker = {}
    self.defaultTargetRor = 10
    self.defaultStopLoss = -5
    self.adjustRor = 2
    self.logicList = logicList
    
  def saveNew(self, symbol):
    self.targetRorChecker[symbol] = [self.defaultTargetRor, self.defaultStopLoss]
    
  def decideGoOrStop(self, data, currentPosition):
    for logic in self.logicList:
      side = logic(data)
      if side == currentPosition:
        continue
      else:
        return 'Stop'
      
    return 'Go'
   
   
  def bet(self, symbol, side):
    # data = get1HData(self.client, symbol, 50)
    # ma = getMa(data)
    # currentSide = ma
    # if side == currentSide:
    if True:
      self.targetRorChecker[symbol] = [self.targetRorChecker[symbol][0]+self.adjustRor-1, self.targetRorChecker[symbol][0]-self.adjustRor]
      return 'bet'
    else:
      return 'close'
  
  def getClosePositions(self, positions):
    list_to_close = []
    for position in positions:
      symbol = position['symbol']
      data = get4HData(self.client, symbol, 50)
      close = getBolingerClose(data, position['side'])
      if close == 'close':
        list_to_close.append(position)
        
    return list_to_close