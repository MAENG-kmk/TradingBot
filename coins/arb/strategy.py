from coins.vb_close_strategy import BaseVBCloseStrategy


class ARBStrategy(BaseVBCloseStrategy):
    """
    ARB 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2023~2026, 포지션 10%):
      ROR +675%  Sharpe 11.17  MDD -1.1%  승률 57.4%  P/L 2.11
    """
    SYMBOL             = "ARBUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 0  # ARB: 정수 단위
