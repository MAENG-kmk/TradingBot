from coins.base_strategy import BaseCoinStrategy


class LINKStrategy(BaseCoinStrategy):
    """LINK 전용 전략 — Robust 최적화 완료 (2026-03-02) | MR 비활성화 (2026-03-22)"""
    SYMBOL = "LINKUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # LINK: 0.1 단위

    # 진입 파라미터 (Optimizer 2026-03-28)
    TR_BB_PERIOD = 20
    TR_BB_STD = 2.5
    RSI_OVERBUY = 80
    RSI_OVERSELL = 30
    ADX_THRESHOLD = 20
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Optimizer 2026-03-28)
    DEFAULT_TARGET_ROR = 7.0
    TRAILING_RATIO = 0.5
    TIGHT_TRAILING_RATIO = 0.85

    # 평균회귀 비활성화 — BB/OU 모두 손실, 추세추종만 운용
    MR_ENABLED = False
