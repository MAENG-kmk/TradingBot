from coins.base_strategy import BaseCoinStrategy


class BNBStrategy(BaseCoinStrategy):
    """BNB 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "BNBUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 2  # BNB: 0.01 단위

    # 진입 파라미터 (Robust 최적화)
    EMA_SHORT = 5
    EMA_LONG = 50
    RSI_OVERBUY = 70
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 20
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 10.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.85
