def decidePosition(ticker):
  percent = sum(ticker['value'])/sum(ticker['quoteVolume'])
  # print("{}%".format(percent))
  if percent > 0:
    return 'long'
  else:
    return 'short'