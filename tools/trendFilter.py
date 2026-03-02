import numpy as np


def calculate_adx(data, period=14):
  """
  ADX (Average Directional Index) 계산
  ADX > 25: 추세장, ADX < 20: 횡보장
  """
  highs = data['High'].values.astype(float)
  lows = data['Low'].values.astype(float)
  closes = data['Close'].values.astype(float)

  n = len(data)
  if n < period * 2 + 1:
    return 0

  # +DM, -DM, TR
  plus_dm = np.zeros(n - 1)
  minus_dm = np.zeros(n - 1)
  tr = np.zeros(n - 1)

  for i in range(n - 1):
    high_diff = highs[i + 1] - highs[i]
    low_diff = lows[i] - lows[i + 1]

    plus_dm[i] = high_diff if (high_diff > low_diff and high_diff > 0) else 0
    minus_dm[i] = low_diff if (low_diff > high_diff and low_diff > 0) else 0

    tr[i] = max(
      highs[i + 1] - lows[i + 1],
      abs(highs[i + 1] - closes[i]),
      abs(lows[i + 1] - closes[i])
    )

  # Wilder's smoothing
  smoothed_tr = np.mean(tr[:period])
  smoothed_plus = np.mean(plus_dm[:period])
  smoothed_minus = np.mean(minus_dm[:period])

  dx_values = []

  for i in range(period, len(tr)):
    smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr[i]
    smoothed_plus = smoothed_plus - (smoothed_plus / period) + plus_dm[i]
    smoothed_minus = smoothed_minus - (smoothed_minus / period) + minus_dm[i]

    plus_di = 100 * smoothed_plus / smoothed_tr if smoothed_tr > 0 else 0
    minus_di = 100 * smoothed_minus / smoothed_tr if smoothed_tr > 0 else 0

    di_sum = plus_di + minus_di
    dx = 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0
    dx_values.append(dx)

  if len(dx_values) < period:
    return 0

  # ADX = Smoothed DX (Wilder's)
  adx = np.mean(dx_values[:period])
  for i in range(period, len(dx_values)):
    adx = (adx * (period - 1) + dx_values[i]) / period

  return adx


def checkTrendStrength(data, adx_threshold=20):
  """
  횡보장 필터 — 확실한 방향성이 있을 때만 True

  ADX 기반 2단계 체크:
    1. ADX > threshold: 확실한 추세 → 진입 허용
    2. ADX 상승 중 (breakout): 추세 형성 중 → 진입 허용
    3. 둘 다 아님: 횡보장 → 진입 금지

  Args:
    data: DataFrame (Open, High, Low, Close, Volume)
    adx_threshold: ADX 기준값 (기본 20)

  Returns:
    bool: True = 추세장 (진입 가능), False = 횡보장 (진입 금지)
  """
  if len(data) < 50:
    return False

  # ADX 계산 (최근 3개 시점)
  adx_current = calculate_adx(data)

  # 확실한 추세
  if adx_current >= adx_threshold:
    return True

  # ADX 상승 중 = breakout 감지 (최근 3봉 연속 상승)
  if adx_current > 15 and len(data) > 52:
    adx_prev1 = calculate_adx(data.iloc[:-1])
    adx_prev2 = calculate_adx(data.iloc[:-2])
    if adx_current > adx_prev1 > adx_prev2:
      return True

  # 횡보장
  return False
