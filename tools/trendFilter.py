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


def calculate_regression_slope(closes, period=20):
  """
  선형 회귀 기울기로 추세 방향 판단

  최근 period 봉의 종가에 대해 최소자승법(OLS) 선형회귀를 수행,
  기울기를 가격 대비 % 변화율로 정규화하여 반환한다.

  Args:
    closes: 종가 배열 (numpy array 또는 list)
    period: 회귀 기간 (기본 20봉)

  Returns:
    float: 정규화된 기울기 (양수=상승추세, 음수=하락추세, 0 근처=횡보)
           단위: 1봉당 가격 변화율(%) — 예) 0.5 → 봉당 0.5% 상승
  """
  if len(closes) < period:
    return 0.0

  y = np.array(closes[-period:], dtype=float)
  x = np.arange(period, dtype=float)

  # OLS: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
  x_mean = x.mean()
  y_mean = y.mean()
  slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)

  # 가격 대비 % 정규화
  if y_mean == 0:
    return 0.0
  return (slope / y_mean) * 100


def checkTrendStrength(data, adx_threshold=20):
  """
  추세 판단 — ADX(강도) + 회귀 기울기(방향) 결합

  Returns:
    bool: True = 추세장 (진입 가능), False = 횡보장 (진입 금지)
  """
  if len(data) < 50:
    return False

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


def checkMarketRegime(data, adx_threshold=20, slope_period=20, slope_threshold=0.05):
  """
  시장 상태 분류 — 추세 강도 + 방향을 함께 판단

  ADX로 추세 강도를, 회귀 기울기로 방향을 판단하여
  'uptrend' / 'downtrend' / 'ranging' 중 하나를 반환.

  Args:
    data: DataFrame (Open, High, Low, Close, Volume)
    adx_threshold: ADX 추세 기준값
    slope_period: 회귀 기울기 계산 기간 (봉 수)
    slope_threshold: 횡보 판단 기울기 임계값 (%)

  Returns:
    tuple: (regime, adx, slope)
      - regime: 'uptrend' | 'downtrend' | 'ranging'
      - adx: 현재 ADX 값
      - slope: 정규화된 회귀 기울기 (%)
  """
  if len(data) < 50:
    return 'ranging', 0, 0.0

  adx_current = calculate_adx(data)
  closes = data['Close'].values.astype(float)
  slope = calculate_regression_slope(closes, slope_period)

  is_trending = checkTrendStrength(data, adx_threshold)

  if is_trending and slope > slope_threshold:
    return 'uptrend', adx_current, slope
  elif is_trending and slope < -slope_threshold:
    return 'downtrend', adx_current, slope
  else:
    return 'ranging', adx_current, slope
