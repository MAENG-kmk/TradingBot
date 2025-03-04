def getVolume(data):
  volumes = data.iloc[-2:]['Volume']
  last_volume = float(volumes.iloc[1])
  past_volume = float(volumes.iloc[0])
  k = 1.2

  if last_volume > past_volume * k:
    return True
  else:
    return False
  