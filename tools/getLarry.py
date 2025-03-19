def getLarry(data):
  k = 0.5
  
  bodys = data.iloc[-2:]
  cur_body = float(bodys.iloc[1]['Body'])
  range = float(bodys.iloc[0]['High'] - bodys.iloc[0]['Low']) * k
  # print('curBody: {}, range: {}'.format(cur_body, range))
  if cur_body > range:
    return 'long'
  elif cur_body < -range:
    return 'short'
  else:
    return 'none'
  