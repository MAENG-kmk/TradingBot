"""
Ornstein-Uhlenbeck 프로세스 파라미터 추정

수식:
  dX = θ(μ - X)dt + σdW

  θ: 평균회귀 속도 (클수록 빠르게 평균으로 돌아옴)
  μ: 장기 평균 (로그가격의 균형점)
  σ: 변동성
  σ_eq = σ/√(2θ): 균형 표준편차 (Z-score 분모)

추정 방법:
  log 가격에 AR(1) OLS 적용
  X(t) = a + b·X(t-1) + ε
  → b = e^(-θ·dt)  →  θ = -ln(b)/dt
  → a = μ(1-b)     →  μ = a/(1-b)
"""
import numpy as np


def fit_ou(prices, dt=1.0):
    """
    OU 파라미터 추정

    Args:
        prices: 종가 배열 (numpy array or list)
        dt:     시간 간격 (봉 단위, 기본 1봉)

    Returns:
        dict | None
          theta     : 평균회귀 속도
          mu        : 장기 평균 (로그 가격)
          sigma     : OU 변동성
          sigma_eq  : 균형 표준편차
          half_life : 반감기 (봉 단위)  — ln(2)/θ
          zscore    : 현재 Z-score      — (log_price - μ) / σ_eq
        None: 평균회귀 성질 없음 (b >= 1) 또는 데이터 부족
    """
    x = np.log(np.asarray(prices, dtype=float))
    if len(x) < 20:
        return None

    # AR(1) OLS
    x_lag = x[:-1]
    x_cur = x[1:]

    xm = x_lag.mean()
    ym = x_cur.mean()
    cov = np.sum((x_lag - xm) * (x_cur - ym))
    var = np.sum((x_lag - xm) ** 2)
    if var == 0:
        return None

    b = cov / var
    a = ym - b * xm

    # b ∈ (0, 1) 이어야 평균회귀
    if b <= 0 or b >= 1:
        return None

    # OU 파라미터
    theta = -np.log(b) / dt
    mu    = a / (1 - b)

    # 잔차 → OU sigma
    resid       = x_cur - (a + b * x_lag)
    sigma_resid = resid.std()
    if sigma_resid == 0:
        return None

    exp_factor = 1 - np.exp(-2 * theta * dt)
    if exp_factor <= 0:
        return None

    sigma    = sigma_resid * np.sqrt(2 * theta / exp_factor)
    sigma_eq = sigma / np.sqrt(2 * theta)
    if sigma_eq == 0:
        return None

    half_life = np.log(2) / theta
    zscore    = (x[-1] - mu) / sigma_eq

    return {
        'theta'    : theta,
        'mu'       : mu,
        'sigma'    : sigma,
        'sigma_eq' : sigma_eq,
        'half_life': half_life,
        'zscore'   : zscore,
    }
