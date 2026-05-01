from coins.vb_close_strategy import BaseVBCloseStrategy


class AVAXStrategy(BaseVBCloseStrategy):
    """
    AVAX 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +7522%  Sharpe 11.51  MDD -1.8%  승률 58.5%  P/L 1.99
    """
    SYMBOL             = "AVAXUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 1  # AVAX: 0.1 단위
