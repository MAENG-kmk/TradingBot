import telegram

tele_token = "5210226721:AAG95BNFRPXRME5MU_ytI_JIx7wgiW1XASU"
chat_id = 5135122806

# updater = Updater(token=tele_token, use_context=True)
# dispatcher = updater.dispatcher

async def send_message(text):
    bot = telegram.Bot(tele_token)
    async with bot:
      await bot.sendMessage(chat_id = chat_id, text = text)
    
# def check(update, context):
#   global portfolio, binance
#   message = ""
#   for ticker in portfolio:
#     text = "{}: {}포지션, 수량:{} \n\n".format(ticker, portfolio[ticker][0], portfolio[ticker][1])
#     message += text
#   balance = binance.fetch_balance()['total']['USDT']
#   message += "\n\n현재 평가 잔고: {:.1f}$".format(balance)
#   context.bot.send_message(chat_id=update.effective_chat.id, text=message)
  
# def stop_trade(update, context):
#     global isRunning
#     context.bot.send_message(chat_id=update.effective_chat.id, text="시스템 중지, 재시작 명령어: start")
#     isRunning = False

# def start_trade():
#     global isRunning, balance, bullet, tickers, portfolio
#     balance = binance.fetch_balance()
#     balance = balance['free']['USDT']
#     bullet = balance / 5
#     tickers = binance.fetch_tickers()
#     portfolio = {}
#     send_message("트레이딩 시작, 잔액: {:.1f}$".format(balance))
    
#     isRunning = True