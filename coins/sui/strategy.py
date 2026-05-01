from coins.vb_close_strategy import BaseVBCloseStrategy


class SUIStrategy(BaseVBCloseStrategy):
    """
    SUI 전용 전략 — 래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산)

    백테스트 성과 (2023~2026, 포지션 10%):
      ROR +1123%  Sharpe 12.56  MDD -0.9%  승률 59.5%  P/L 2.11
    """
    SYMBOL             = "SUIUSDT"
    LEVERAGE           = 1
    QUANTITY_PRECISION = 0  # SUI: 정수 단위
