from binance.client import Client
from binance import ThreadedWebsocketManager
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET, COLLECTION

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)

from tools.BetController import BetController
from tools.BetControllerTurtle import BetControllerTurtle
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.getData import getData, getUsaTimeData, get1HData, get4HData, get1MData
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
from tools.linearRegression import linearRegression
from tools.getAtr import getATR
from tools.makeIsolated import makeIsolated
from tools.getMaxLeverage import getMaxLeverage

from logics.decidePosition import decidePosition
from logics.closePosition import closePosition
from logics.enterPosition import enterPosition
from logics.enterPositionTurtle import enterPositionTurtle

from MongoDB_python.client import addVersionAndDate
import math
import asyncio
import time
import websocket
import json
from collections import deque
from datetime import datetime

class HFT:
  def __init__(self):
    self.R = 0.05
    self.leverage = 75
    self.fee = 0.001
    self.targetRor = 2 / self.leverage
    self.stopRor = -1 / self.leverage
    self.gapRor = 0.1 / self.leverage
    self.qty = 0
    self.isEntered = False
    self.logic_list = [getMACD]
    self.targetPrice = 0
    self.stopPrice = 0
    self.gap = 0
    self.twm = None
    self.trailing = False
  
  def clear(self):
    self.leverage = 75
    self.qty = 0
    self.isEntered = False
    self.targetRor = 2 / self.leverage
    self.stopRor = -1 / self.leverage
    self.gapRor = 0.1 / self.leverage
    self.targetPrice = 0
    self.stopPrice = 0
    self.gap = 0
    self.twm = None
    self.trailing = False
    
  def logic_filter(self, data):
    result = 'None'
    for logic in self.logic_list:
      side = logic(data)
      if side == 'None':
        break
      if side == result:
        continue
      elif  result == 'None':
        result = side
      else:
        result = 'None'
        break
    return result
  
  def setParams(self, leverage):
    self.leverage = leverage
    self.targetRor = 2 / self.leverage
    self.stopRor = -1 / self.leverage
    self.gapRor = 0.1 / self.leverage
    
  def enter(self):
    ticker = getTicker(client)
    for _, coin in ticker.iterrows():
      symbol = coin['symbol']
      data = get1MData(client, symbol, 50)
      if len(data) < 49:
        continue
      atr = getATR(data)
      targetRor = abs(atr/data.iloc[-1]['Close'])*100
      if targetRor < 1:
        continue
      check_volume = getVolume(data)
      if not check_volume or symbol[-4:] != 'USDT':
        continue
          
      way = self.logic_filter(data)
      if way == 'None':
        continue
      data_1h = get1HData(client, symbol, 50)
      check = getMa(data_1h)
      if way != check:
        continue
      
      balance, _ = getBalance(client)
      bullet = float(balance) * 0.99 * self.R * self.leverage
      
      leverage_max = getMaxLeverage(client, symbol)
      self.setParams(leverage_max)
      
      makeIsolated(client, symbol)
      setLeverage(client, symbol, self.leverage)
          
      lastQty = coin['lastQty'].split('.')
      if len(lastQty) == 1:
        point = 0
        amount = math.floor((bullet / float(coin['lastPrice'])) )
      else:
        point = len(lastQty[1])
        amount = math.floor((bullet / float(coin['lastPrice'])) * (10**point)) / (10**point)
      if amount < 10**(-point):
        continue
      self.qty = amount
      if way == 'long':
        createOrder(client, symbol, 'BUY', 'MARKET', amount)
        self.isEntered = True
        self.close(symbol, way)
        
      elif way == 'short':
        createOrder(client, symbol, 'SELL', 'MARKET', amount)
        self.isEntered = True
        self.close(symbol, way)
        
        
        
  def close(self, symbol, side):
    position = getPositions(client)
    if position:   
      enterPrice = float(position[0]['enterPrice'])
    else:
      self.close(symbol, side)
      return
    if side == 'long':
      self.targetPrice = enterPrice * (1 + self.targetRor + self.fee)
      self.stopPrice = enterPrice * (1 + self.stopRor + self.fee)
      self.gap = enterPrice * self.gapRor
    elif side == 'short':
      self.targetPrice = enterPrice * (1 - self.targetRor - self.fee)
      self.stopPrice = enterPrice * (1 - self.stopRor - self.fee)
      self.gap = enterPrice * self.gapRor
    print('close시작, symbol: {}, curPrice: {}, target: {}, stop: {}'.format(symbol, enterPrice, self.targetPrice, self.stopPrice), side)
    def on_message(ws, message):
        try:
          msg = json.loads(message)
          if 'result' in msg and 'id' in msg:
              print(f"Subscription confirmed for {symbol}: {msg}")
              return
            
          if 'e' in msg and msg['e'] == 'error':
              print(f"WebSocket error for {symbol}: {msg.get('m', 'Unknown error')}")
              ws.close()
              return
            
          bid_price = float(msg['b'])
          ask_price = float(msg['a'])
          current_price = bid_price if side == 'long' else ask_price

          if side == 'long':
            if current_price >= self.targetPrice:
              self.targetPrice = current_price
              self.stopPrice = current_price - self.gap
              self.trailing = True
            elif current_price <= self.stopPrice:
              if self.trailing:
                 createOrder(client, symbol, 'SELL', 'MARKET', self.qty)
                 self.clear()
                 ws.close()
              else:
                positions = getPositions(client)
                if len(positions) == 0:
                  self.clear()
                  ws.close()
          elif side == 'short':
            if current_price <= self.targetPrice:
              self.targetPrice = current_price
              self.stopPrice = current_price + self.gap
              self.trailing = True
            elif current_price >= self.stopPrice:
              if self.trailing:
                 createOrder(client, symbol, 'BUY', 'MARKET', self.qty)
                 self.clear()
                 ws.close()
              else:
                positions = getPositions(client)
                if len(positions) == 0:
                  self.clear()
                  ws.close()

        except Exception as e:
            print(f"Error in WebSocket message handling for {symbol}: {e}")
            ws.close()

    def on_error(ws, error):
      print(f"WebSocket error for {symbol}: {error}")
      ws.close()

    def on_close(ws, close_status_code, close_msg):
      print(f"WebSocket closed for {symbol}: {close_status_code}, {close_msg}")
      self.isEntered = False

    def on_open(ws):
      ws.send(json.dumps({
          "method": "SUBSCRIBE",
          "params": [f"{symbol.lower()}@bookTicker"],
          "id": 1
      }))

    ws_url = "wss://fstream.binance.com/ws"
    self.ws = websocket.WebSocketApp(ws_url,
                                     on_message=on_message,
                                     on_error=on_error,
                                     on_close=on_close,
                                     on_open=on_open)

    while self.isEntered:
        try:
            self.ws.run_forever()
            break
        except Exception as e:
            print(f"WebSocket reconnecting for {symbol}: {e}")
            time.sleep(5)  # Wait before reconnecting
    
  def run(self):
    while not self.isEntered:
      self.enter()
      time.sleep(10)

balance, available = getBalance(client)
# addVersionAndDate(COLLECTION, balance)

hft = HFT()
hft.run()