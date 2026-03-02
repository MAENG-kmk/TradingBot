from coins.base_strategy import BaseCoinStrategy


class XRPStrategy(BaseCoinStrategy):
    """XRP 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "XRPUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # XRP: 정수 단위

    # 진입 파라미터 (최적화)
    EMA_SHORT = 10
    EMA_LONG = 30
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 3.0

    # 청산 파라미터 (최적화)
    TARGET_ROR_PCT = 15.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.85
