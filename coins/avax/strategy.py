from coins.base_strategy import BaseCoinStrategy


class AVAXStrategy(BaseCoinStrategy):
    """AVAX 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "AVAXUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # AVAX: 0.1 단위

    # 진입 파라미터 (Robust 최적화)
    TR_BB_PERIOD = 20
    TR_BB_STD = 2.0
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 15
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Robust 최적화)
    DEFAULT_TARGET_ROR = 15.0
    TRAILING_RATIO = 0.4
    TIGHT_TRAILING_RATIO = 0.85

    # OU 평균회귀 파라미터 (2026-03-22)
    MR_ENABLED = True
    MR_OU_ENTRY_Z = 1.8       # AVAX 회귀 빠름, 조금 낮게 설정
    MR_OU_EXIT_Z = 0.5
    MR_MAX_HALFLIFE = 12
    MR_TIME_HALFLIFE_MULT = 2.5
