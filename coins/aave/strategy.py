from coins.base_strategy import BaseCoinStrategy


class AAVEStrategy(BaseCoinStrategy):
    """AAVE 전용 전략 — TR+VB 3단계 Grid Search 최적화 (2026-04-26)

    백테스트 성과 (4H 기준):
      ROR +53.6%  Sharpe 0.43  MDD -26.7%
    """
    SYMBOL = "AAVEUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # AAVE: 0.1 단위

    # TR 진입 파라미터
    TR_BB_PERIOD = 20
    TR_BB_STD = 2.0
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 2.0

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 10.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.65

    # VB 진입 파라미터
    VB_K = 0.5
    VB_MIN_RANGE_PCT = 0.1

    # OU 평균회귀
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
