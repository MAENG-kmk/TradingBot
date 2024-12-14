import pandas as pd
import numpy as np

def getRsi(data):
  au = 0
  ad = 0
  for i in data.iloc[-2:-16:-1]['Body']:
      if i >= 0:
          au += i
      else:
          ad += -i
  au /= 14
  ad /= 14
  cur =  data.iloc[-1]['Body']
  if cur > 0:
      au = (13 * au + cur) / 14
      ad = ad * 13 / 14
  else:
      au = au * 13 / 14
      ad = (13 * ad - cur) / 14
  
  if ad != 0:
    rs = au / ad
  else:
    rs = 100
  rsi = rs / ( 1 + rs) * 100
  
  return rsi