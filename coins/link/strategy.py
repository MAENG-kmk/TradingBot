from coins.vb_close_strategy import BaseVBCloseStrategy


class LINKStrategy(BaseVBCloseStrategy):
    """
    LINK 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2020~2026, 포지션 10%):
      ROR +3548%  Sharpe 11.28  MDD -1.4%  승률 57.5%  P/L 2.00
    """
    SYMBOL             = "LINKUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 1  # LINK: 0.1 단위
