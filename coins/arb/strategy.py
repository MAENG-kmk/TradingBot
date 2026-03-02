from coins.base_strategy import BaseCoinStrategy


class ARBStrategy(BaseCoinStrategy):
    """ARB 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "ARBUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # ARB: 정수 단위

    # 진입 파라미터 (Robust 최적화)
    EMA_SHORT = 20
    EMA_LONG = 50
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 10.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.65
