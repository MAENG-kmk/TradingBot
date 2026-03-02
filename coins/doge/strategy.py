from coins.base_strategy import BaseCoinStrategy


class DOGEStrategy(BaseCoinStrategy):
    """DOGE 전용 전략 — Robust 최적화 완료 (2026-03-01)"""
    SYMBOL = "DOGEUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # DOGE: 정수 단위

    # 진입 파라미터 (Robust 최적화 - 5개 기간 모두 수익)
    EMA_SHORT = 10
    EMA_LONG = 50
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 20
    ATR_MULTIPLIER = 2.0

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 15.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.85
