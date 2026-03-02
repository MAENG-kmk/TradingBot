from coins.base_strategy import BaseCoinStrategy


class SOLStrategy(BaseCoinStrategy):
    """SOL 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "SOLUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # SOL: 0.1 단위

    # 진입 파라미터 (Robust 최적화)
    EMA_SHORT = 20
    EMA_LONG = 50
    RSI_OVERBUY = 70
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 25
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 15.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.75
