from coins.base_strategy import BaseCoinStrategy


class SUIStrategy(BaseCoinStrategy):
    """SUI 전용 전략 — TR+VB 3단계 Grid Search 최적화 (2026-04-26)

    백테스트 성과 (2023-05~2026-04, 4H 기준):
      ROR +77.8%  Sharpe 5.85  MDD -23.6%
    """
    SYMBOL = "SUIUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 0  # SUI: 정수 단위

    # TR 진입 파라미터
    TR_BB_PERIOD = 15
    TR_BB_STD = 1.5
    RSI_OVERBUY = 70
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 2.0

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 15.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.65

    # VB 진입 파라미터
    VB_K = 0.2
    VB_MIN_RANGE_PCT = 0.1

    # OU 평균회귀
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
