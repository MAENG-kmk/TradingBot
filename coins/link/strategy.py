from coins.base_strategy import BaseCoinStrategy


class LINKStrategy(BaseCoinStrategy):
    """LINK 전용 전략 — Robust 최적화 완료 (2026-03-02)"""
    SYMBOL = "LINKUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 1  # LINK: 0.1 단위

    # 진입 파라미터 (Robust 최적화)
    TR_BB_PERIOD = 20
    TR_BB_STD = 2.0
    RSI_OVERBUY = 70
    RSI_OVERSELL = 20
    ADX_THRESHOLD = 30
    ATR_MULTIPLIER = 1.5

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 15.0
    TRAILING_RATIO = 0.7
    TIGHT_TRAILING_RATIO = 0.65
