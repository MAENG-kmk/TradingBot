from coins.vb_close_strategy import BaseVBCloseStrategy


class DOGEStrategy(BaseVBCloseStrategy):
    """
    DOGE 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%, close 모드):
      ROR +3607%  Sharpe 9.44  MDD -8.7%  승률 56.7%  P/L 2.12
    """
    SYMBOL             = "DOGEUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 0  # DOGE: 정수 단위
