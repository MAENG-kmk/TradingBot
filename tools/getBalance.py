def getBalance(client):
  balance = client.futures_account_balance()
  for asset in balance:
    if asset['asset'] == 'USDT':
      return asset['balance'], asset['availableBalance']
  return 0, 0