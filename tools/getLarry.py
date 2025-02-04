def getLarry(data):
  k = 0.5
  
  bodys = data.iloc[-2:]['Body']
  cur_body = float(bodys.iloc[1])
  range = abs(float(bodys.iloc[0])) * k

  if cur_body > range:
    return 'long'
  elif cur_body < -range:
    return 'short'
  else:
    return 'none'
  