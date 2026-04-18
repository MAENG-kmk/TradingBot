from coins.base_strategy import BaseCoinStrategy


class AAVEStrategy(BaseCoinStrategy):
    """AAVE 전용 전략 — XGB+VB Grid Search 최적화 (2026-04-17)"""
    SYMBOL = "AAVEUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # AAVE: 0.1 단위

    # 진입 파라미터
    TR_BB_PERIOD = 25
    TR_BB_STD = 1.5
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 3.0

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 7.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.65

    # VB 파라미터
    VB_K = 0.2
    VB_MIN_RANGE_PCT = 0.3
