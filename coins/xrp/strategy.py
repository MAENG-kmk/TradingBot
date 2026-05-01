from coins.vb_close_strategy import BaseVBCloseStrategy


class XRPStrategy(BaseVBCloseStrategy):
    """
    XRP 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +1523%  Sharpe 9.11  MDD -1.6%  승률 54.1%  P/L 2.03
    """
    SYMBOL             = "XRPUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 0  # XRP: 정수 단위
