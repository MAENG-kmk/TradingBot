from coins.base_strategy import BaseCoinStrategy


class ARBStrategy(BaseCoinStrategy):
    """ARB 전용 전략 — XGB+VB Grid Search 최적화 (2026-04-17)"""
    SYMBOL = "ARBUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # ARB: 정수 단위

    # 진입 파라미터
    TR_BB_PERIOD = 20
    TR_BB_STD = 1.5
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 10
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 7.0
    TRAILING_RATIO = 0.6
    TIGHT_TRAILING_RATIO = 0.65

    # VB 파라미터
    VB_K = 0.2
    VB_MIN_RANGE_PCT = 0.2
