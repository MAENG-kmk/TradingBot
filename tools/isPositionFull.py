def isPositionFull(total, available):
  if float(available) < float(total) / 10:
    return True
  else:
    return False