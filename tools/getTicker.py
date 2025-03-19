import pandas as pd

def getTicker(client): 
  tickers = client.futures_ticker()
  df = pd.DataFrame(tickers)
  df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
  df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'])
  df['priceChangePercentAbs'] = abs(df['priceChangePercent'])
  df['value'] = df['quoteVolume'] * df['priceChangePercent']  
  df = df.sort_values(by=['quoteVolume'], ascending=False)
  df = df.iloc[:150]
  df = df.sort_values(by=['priceChangePercentAbs'], ascending=False)
  
  return df
  