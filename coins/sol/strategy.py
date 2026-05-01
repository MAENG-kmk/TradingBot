from coins.vb_close_strategy import BaseVBCloseStrategy


class SOLStrategy(BaseVBCloseStrategy):
    """
    SOL 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +6465%  Sharpe 11.42  MDD -2.3%  승률 58.4%  P/L 2.00
    """
    SYMBOL             = "SOLUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 1  # SOL: 0.1 단위
