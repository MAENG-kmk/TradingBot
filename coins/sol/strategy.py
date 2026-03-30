from coins.base_strategy import BaseCoinStrategy


class SOLStrategy(BaseCoinStrategy):
    """SOL 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "SOLUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # SOL: 0.1 단위

    # 진입 파라미터 (Optimizer 2026-03-28)
    TR_BB_PERIOD = 15
    TR_BB_STD = 2.5
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Optimizer 2026-03-28)
    DEFAULT_TARGET_ROR = 7.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.85

    # OU 평균회귀 파라미터 (2026-03-22)
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 2.0
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 10      # SOL 변동성 감안해 조금 타이트하게
    MR_TIME_HALFLIFE_MULT = 2.5
