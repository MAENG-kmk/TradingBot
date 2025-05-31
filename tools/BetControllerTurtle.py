class BetControllerTurtle:
  def __init__(self, client, logicList):
    self.client = client
    self.targetRorChecker = {}
    self.defaultTargetRor = 10
    self.defaultStopLoss = -5
    self.adjustRor = 1
    self.logicList = logicList
    
    self.step = 0.02
    self.symbol = ''
    self.side = 'none'
    self.enterPrice = 0
    self.firePrice = 0
    self.closePrice = 0
    self.isFull = False
    
  def saveNew(self, symbol, side, enterPrice):
    self.symbol = symbol
    self.enterPrice = float(enterPrice)
    self.side = side
    if side == 'long':
      self.firePrice = self.enterPrice * (1 + self.step)
      self.closePrice = self.enterPrice * (1 - self.step)
    elif side == 'short':
      self.firePrice = self.enterPrice * (1 - self.step)
      self.closePrice = self.enterPrice * (1 + self.step)
  
  def clear(self):
    self.symbol = ''
    self.side = 'none'
    self.enterPrice = 0
    self.firePrice = 0
    self.closePrice = 0
    self.isFull = False
   
  def bet(self, symbol, side):
    # data = get1HData(self.client, symbol, 50)
    # ma = getMa(data)
    # currentSide = ma
    # if side == currentSide:
    if True:
      if side == 'long':
        self.firePrice = self.firePrice * (1 + self.step)
        self.closePrice = self.firePrice / (1 + self.step) ** 2
      else:
        self.firePrice = self.firePrice * (1 - self.step)
        self.closePrice = self.firePrice / (1 - self.step) ** 2
      return 'bet'
    else:
      return 'close'
  
  def getClosePositions(self, positions):
    list_to_close = []
    symbol = self.symbol
    position = positions[0]
    curPrice = position['markPrice']
    if position['symbol'] != symbol:
      return list_to_close
    
    if self.side == 'long':
      if curPrice < self.closePrice:
        list_to_close.append(position)
      if self.isFull:
        if curPrice > self.firePrice:
          betting = self.bet(symbol, self.side)
        elif curPrice < self.closePrice:
          list_to_close.append(position)
    elif self.side == 'short':
      if curPrice > self.closePrice:
        list_to_close.append(position)
      if self.isFull:
        if curPrice < self.firePrice:
          betting = self.bet(symbol, self.side)
        elif curPrice > self.closePrice:
          list_to_close.append(position)
        
    return list_to_close