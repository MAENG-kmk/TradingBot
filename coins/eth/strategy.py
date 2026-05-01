from coins.vb_close_strategy import BaseVBCloseStrategy


class ETHStrategy(BaseVBCloseStrategy):
    """
    ETH 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +1073%  Sharpe 9.75  MDD -0.9%  승률 53.4%  P/L 2.10
    """
    SYMBOL             = "ETHUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 2  # ETH: 0.01 단위
