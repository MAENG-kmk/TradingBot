def getVolume(data):
  data['Volume_3'] = data['Volume'].rolling(window=3).mean()
  data['Volume_7'] = data['Volume'].rolling(window=7).mean()

  k = 1.5
  vol_3 = data.iloc[-1]['Volume_3']
  vol_7 = data.iloc[-1]['Volume_7']

  if vol_3 > vol_7 * k:
    return True
  else:
    return False
  # if last_volume > past_volume * k:
  #   return True
  # else:
  #   return False
  