def checkRisk(data):
  data['Change'] = data['High'] - data['Low']
  data['Body_5'] = data['Change'].rolling(window=5).mean()
  data['Body_20'] = data['Change'].rolling(window=20).mean()
  cur = data.iloc[-1]['Body_5']
  last = data.iloc[-1]['Body_20']
  
  k = 5
  if cur  > last * k:
    return False
  else:
    return True