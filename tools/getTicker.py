import pandas as pd

def getTicker(client): 
  tickers = client.futures_ticker()
  df = pd.DataFrame(tickers)
  df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
  df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'])
  df['value'] = df['quoteVolume'] * df['priceChangePercent']  
  df = df.sort_values(by=['quoteVolume'], ascending=False)
  df = df.iloc[:100]
  df = df.sort_values(by=['priceChangePercent'], ascending=False)
  
  return df
  