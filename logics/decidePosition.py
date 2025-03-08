def decidePosition(ticker, BTC_data, getMa):
  # percent = sum(ticker['value'])/sum(ticker['quoteVolume'])
  ma = getMa(BTC_data)
  return ma
  # if percent > 0:
  #   return 'long'
    # if ma == 'long':
    #   return 'long'
    # else:
    #   return 'None'
  # else:
  #   return 'short'
    # if ma == 'short':
    #   return 'short'
    # else:
    #   return 'None'
    
