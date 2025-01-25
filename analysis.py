f = open('./data.txt')
lines = f.readlines()
datas = []
data = []
for line in lines:
  l = line.split()
  if len(l) == 0:
    if data:
      datas.append(data)
    data = []
  elif l[0] == 'symbol:':
    ror = float(l[3].split('%')[0])
    profit = float(l[5].split('$')[0])
    balance = float(l[7])
    data.append(ror)
    data.append(profit)
    data.append(balance)
  elif l[0] == 'side:':
    side = l[1]
    if side == '0,':
      data = []
      continue
    rsi = float(l[4][:-1])
    data.append(side)
    data.append(rsi)
  else:
    continue

x = 0
x_ = 0
y = 0
y_ = 0
for data in datas:
  if data[3] == 'long,':
    if data[0] > 0:
      x += 1
    else:
      x_ += 1
  else:
    if data[0] > 0:
      y += 1
    else:
      y_ += 1

print(x, x_)
print(y, y_)