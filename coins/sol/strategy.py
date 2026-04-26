from coins.base_strategy import BaseCoinStrategy


class SOLStrategy(BaseCoinStrategy):
    """SOL 전용 전략 — TR+VB 3단계 Grid Search 최적화 (2026-04-26)

    백테스트 성과 (4H 기준):
      ROR +184%  Sharpe 1.18  MDD -16.1%
    """
    SYMBOL = "SOLUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # SOL: 0.1 단위

    # TR 진입 파라미터
    TR_BB_PERIOD = 25
    TR_BB_STD = 2.5
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 15.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.75

    # VB 진입 파라미터
    VB_K = 0.2
    VB_MIN_RANGE_PCT = 0.1

    # OU 평균회귀
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
