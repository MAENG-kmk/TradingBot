def getVolume(data):
  volumes = data.iloc[-2:]['Volume']
  last_volume = int(volumes.iloc[1])
  past_volume = int(volumes.iloc[0])
  k = 1.5
  if last_volume > past_volume * k:
    return True
  else:
    return False
  
  