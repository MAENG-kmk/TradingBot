"""
SDE (Stochastic Differential Equation) 기반 트레이딩 도구

GBM(Geometric Brownian Motion) 파라미터 추정과
이중 장벽 도달 확률(Double Barrier Crossing Probability) 계산을 제공한다.

핵심 수식:
  log-price 변화: X_t = ν·t + σ·W_t
  Itô 보정 드리프트: ν = μ - σ²/2
  장벽 도달 확률 (closed-form):
    k = 2ν/σ²
    a = ln(S_target / S)  > 0
    b = ln(S_stop   / S)  < 0
    P(hit a before b) = (e^{-k·b} - 1) / (e^{-k·b} - e^{-k·a})   if k ≠ 0
                      = |b| / (a + |b|)                             if k = 0
"""

import numpy as np


def barrier_prob(S, S_target, S_stop, mu_bar, sigma_bar):
    """
    GBM 이중 장벽 도달 확률: P(price hits S_target before S_stop | current = S)

    전제: S_target > S > S_stop  (롱 방향 기준)
    숏 방향은 호출 측에서 1 - barrier_prob(S, S_stop_short, S_target_short, mu, sigma) 로 계산.

    Args:
        S          : 현재가
        S_target   : 목표가 (상단 장벽)
        S_stop     : 손절가 (하단 장벽)
        mu_bar     : 봉당 log 수익률 평균 (GBM μ, raw)
        sigma_bar  : 봉당 log 수익률 표준편차 (GBM σ)

    Returns:
        float: 확률 [0.0, 1.0]
    """
    if sigma_bar <= 1e-10 or S <= 0:
        return 0.5
    if S >= S_target:
        return 1.0
    if S <= S_stop:
        return 0.0

    a = np.log(S_target / S)   # > 0
    b = np.log(S_stop   / S)   # < 0

    if abs(a - b) < 1e-10:
        return 0.5

    nu = mu_bar - 0.5 * sigma_bar ** 2   # Itô corrected drift
    k  = 2.0 * nu / (sigma_bar ** 2)

    # k ≈ 0 → 드리프트 없는 랜덤워크 근사
    if abs(k) < 1e-8:
        return abs(b) / (a + abs(b))

    try:
        exp_neg_kb = np.exp(-k * b)
        exp_neg_ka = np.exp(-k * a)

        if not (np.isfinite(exp_neg_kb) and np.isfinite(exp_neg_ka)):
            return 1.0 if nu > 0 else 0.0

        num = exp_neg_kb - 1.0
        den = exp_neg_kb - exp_neg_ka

        if abs(den) < 1e-10:
            return abs(b) / (a + abs(b))

        return float(np.clip(num / den, 0.0, 1.0))

    except Exception:
        return 0.5


def estimate_gbm(prices, window=50):
    """
    최근 N봉의 종가로 GBM 파라미터 (μ, σ) 추정 (MLE)

    Args:
        prices : array-like, 종가 시계열 (시간순)
        window : 추정에 사용할 봉 수

    Returns:
        (mu, sigma): 봉당 log 수익률 평균·표준편차
                     추정 불가 시 (None, None)
    """
    arr = np.asarray(prices, dtype=float)
    if len(arr) < window + 1:
        return None, None

    recent = arr[-(window + 1):]
    log_ret = np.diff(np.log(recent))

    mu    = float(np.mean(log_ret))
    sigma = float(np.std(log_ret, ddof=1))

    if sigma < 1e-10:
        return None, None

    return mu, sigma


def sde_entry_probs(S, target_ror, stop_ror, mu, sigma):
    """
    현재가 S에서 롱·숏 진입 확률을 동시에 계산

    Args:
        S          : 현재가
        target_ror : 목표 수익률 (소수, e.g. 0.04)
        stop_ror   : 손절 비율  (소수, e.g. 0.02)
        mu, sigma  : GBM 파라미터 (봉당)

    Returns:
        (p_long, p_short): 각 방향의 목표 도달 확률
    """
    S_target_long  = S * (1.0 + target_ror)
    S_stop_long    = S * (1.0 - stop_ror)
    S_target_short = S * (1.0 - target_ror)
    S_stop_short   = S * (1.0 + stop_ror)

    p_long  = barrier_prob(S, S_target_long,  S_stop_long,  mu,  sigma)
    # 숏: P(hit lower target before upper stop) = 1 - P(hit upper stop before lower target)
    p_short = 1.0 - barrier_prob(S, S_stop_short, S_target_short, mu, sigma)

    return p_long, p_short
