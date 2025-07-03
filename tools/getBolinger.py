def getBolinger(data):
  window = 20
  num_std = 2
  
  df = data.copy()

  # 이동평균(Middle Band)
  df['Middle'] = df['Close'].rolling(window=window).mean()
    
  # 표준편차(Standard Deviation)
  df['Std'] = df['Close'].rolling(window=window).std()

  # 상단밴드 (Upper Band) = Middle + (표준편차 × num_std)
  df['Upper'] = df['Middle'] + (df['Std'] * num_std)

  # 하단밴드 (Lower Band) = Middle - (표준편차 × num_std)
  df['Lower'] = df['Middle'] - (df['Std'] * num_std)

  cur = df.iloc[-1]
  last = df.iloc[-2]
  
  if cur['Close'] > cur['Upper']:
    return 'long'
  elif cur['Close'] < cur['Lower']:
    return 'short'
  else:
    return 'None'

def getBolingerClose(data, side):
  window = 20
  num_std = 2
  
  df = data.copy()

  # 이동평균(Middle Band)
  df['Middle'] = df['Close'].rolling(window=window).mean()
    
  # 표준편차(Standard Deviation)
  df['Std'] = df['Close'].rolling(window=window).std()

  # 상단밴드 (Upper Band) = Middle + (표준편차 × num_std)
  df['Upper'] = df['Middle'] + (df['Std'] * num_std)

  # 하단밴드 (Lower Band) = Middle - (표준편차 × num_std)
  df['Lower'] = df['Middle'] - (df['Std'] * num_std)

  cur = df.iloc[-1]
  
  if side == 'long':
    if  cur['Close'] <= cur['Middle']:
      return 'close'
    else:
      return 'none'
  else:
    if  cur['Close'] >= cur['Middle']:
      return 'close'
    else:
      return 'none'
