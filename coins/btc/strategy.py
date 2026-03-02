from coins.base_strategy import BaseCoinStrategy


class BTCStrategy(BaseCoinStrategy):
    """BTC 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "BTCUSDT"
    LEVERAGE = 2
    QUANTITY_PRECISION = 3  # BTC: 0.001 단위

    # 진입 파라미터 (Robust 최적화)
    EMA_SHORT = 5
    EMA_LONG = 20
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 30
    ATR_MULTIPLIER = 3.0

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 7.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.75
