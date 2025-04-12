f = open('./data.txt')
lines = f.readlines()
datas = []
ror_data = []
balance_data = []

for line in lines:
  l = line.split()
  if l:
    if l[0] == 'ror:':
      ror = float(l[1][:-2])
      ror_data.append(ror)
    elif l[0] == 'balance:':
      balance = float(l[1])
      balance_data.append(balance)



import matplotlib.pyplot as plt
print('매매 횟수:', len(ror_data))
print('평균 수익률:', sum(ror_data)/len(ror_data))

# x = [i-6 for i in range(1, len(ror_data)+1)]
# y = ror_data
# plt.bar(x, y)
# plt.xlabel('profit')
# plt.ylabel('number')
# plt.title('result of trading')
# plt.show()

