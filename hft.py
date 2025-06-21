import websocket
import json
from collections import deque
from datetime import datetime

volume = 0
queue = deque([])
history = []

def on_message(ws, message):
    global volume
    data = json.loads(message)
    if data['m'] == True:
      volume += float(data['q'])
    else:
      volume -= float(data['q'])
    if len(queue) < 100:
      queue.append(volume)
    else:
      queue.popleft()
      queue.append(volume)
    decrease = queue[-1] - max(queue)
    increase = queue[-1] - min(queue)
    if decrease < -20:
      history.append([decrease, datetime.now()])
    if increase > 20:
      history.append([increase, datetime.now()])
    print(decrease)
    print(increase)
      

def on_open(ws):
    print("WebSocket 연결 성공")
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@trade"],  # 실시간 체결 데이터
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))
    
def on_close(ws, close_status_code, close_msg):
  for a in history:
    print(a)

ws = websocket.WebSocketApp(
    "wss://fstream.binance.com/ws/btcusdt@trade",
    on_message=on_message,
    on_open=on_open,
    on_close=on_close
)

ws.run_forever()