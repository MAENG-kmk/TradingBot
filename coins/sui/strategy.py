from coins.base_strategy import BaseCoinStrategy


class SUIStrategy(BaseCoinStrategy):
    """SUI 전용 전략 — 기본 파라미터 (최적화 필요)"""
    SYMBOL = "SUIUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # SUI: 정수 단위

    # 진입 파라미터 (기본값, 추후 Grid Search 최적화 권장)
    TR_BB_PERIOD = 20
    TR_BB_STD = 2.0
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 20
    ATR_MULTIPLIER = 2.0

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 10.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.75

    # OU 평균회귀 (VB로 대체되므로 실질적으로 미사용)
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
