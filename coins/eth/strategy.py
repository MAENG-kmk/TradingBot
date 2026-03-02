from coins.base_strategy import BaseCoinStrategy


class ETHStrategy(BaseCoinStrategy):
    """
    ETH 전용 전략 — Robust 최적화 완료 (2026-03-02)

    Robust 성과 (5기간):
      +7.8% / +26.2% / +12.0% / +25.8% / +76.9%
      avg=29.8%, min=+7.8%, 손실기간 0/5
    """
    SYMBOL = "ETHUSDT"
    LEVERAGE = 1
    QUANTITY_PRECISION = 2  # ETH: 0.01 단위

    # 진입 파라미터 (Robust 최적화)
    EMA_SHORT = 10
    EMA_LONG = 30
    RSI_PERIOD = 14
    RSI_OVERBUY = 70
    RSI_OVERSELL = 30
    ATR_MULTIPLIER = 2.0
    ADX_THRESHOLD = 15

    # 청산 파라미터 (Robust 최적화)
    TARGET_ROR_PCT = 15.0
    TRAILING_RATIO = 0.6
    TIGHT_TRAILING_RATIO = 0.65
