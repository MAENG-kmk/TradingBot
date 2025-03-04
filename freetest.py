def hi():
  print('hi')
  
def hello():
  print('hello')
  
def bye():
  print('bye')

def col(*args):
  for a in args:
    a()
col(hi, hello, bye)