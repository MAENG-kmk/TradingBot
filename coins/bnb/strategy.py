from coins.base_strategy import BaseCoinStrategy


class BNBStrategy(BaseCoinStrategy):
    """BNB 전용 전략 — MTF EMA 9/21 + Regime + VB 최적화 (2026-04-26)

    백테스트 성과 (1H 기준):
      ROR +197.3%  Sharpe 3.95  MDD -4.5%
    """
    SYMBOL = "BNBUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 2  # BNB: 0.01 단위

    # TR 진입 파라미터
    TR_BB_PERIOD = 25
    TR_BB_STD = 2.0
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 3.0

    # 청산 파라미터
    DEFAULT_TARGET_ROR = 7.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.85

    # VB 진입 파라미터
    VB_K = 0.2
    VB_MIN_RANGE_PCT = 0.2

    # OU 평균회귀
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
