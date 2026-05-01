from coins.vb_close_strategy import BaseVBCloseStrategy


class BNBStrategy(BaseVBCloseStrategy):
    """
    BNB 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +891%  Sharpe 8.85  MDD -1.7%  승률 53.6%  P/L 2.11
    """
    SYMBOL             = "BNBUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 2  # BNB: 0.01 단위
