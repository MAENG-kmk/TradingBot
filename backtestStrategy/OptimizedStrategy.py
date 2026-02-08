import backtrader as bt
import numpy as np


class OptimizedStrategy(bt.Strategy):
    """
    EMA + RSI + ATR 기반 최적화 전략
    - EMA: 트렌드 방향 확인
    - RSI: 과매수/과매도 필터
    - ATR: 동적 손절매 및 포지션 사이징
    """
    params = dict(
        ema_short=10,
        ema_long=30,
        rsi_period=14,
        rsi_overbuy=80,    # 70 → 80 (더 극단적)
        rsi_oversell=20,   # 30 → 20 (더 극단적)
        atr_period=14,
        atr_multiplier=2.2,
        take_profit_pct=0.07,
        risk_percent=0.02,
        trailing_stop_pct=0.02,
    )

    def __init__(self):
        # 지표 설정
        self.ema_short = bt.ind.EMA(self.data.close, period=self.p.ema_short)
        self.ema_long = bt.ind.EMA(self.data.close, period=self.p.ema_long)
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.macd = bt.ind.MACD(self.data.close)
        
        # 거래 정보
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.position_size = 0
        self.highest_price = 0

    def next(self):
        # 현재 포지션이 없을 때
        if not self.position:
            # ===== 롱 진입 조건 =====
            if (self.ema_short[0] > self.ema_long[0] and
                self.rsi[0] < self.p.rsi_overbuy and
                self.rsi[0] > self.p.rsi_oversell and
                self.macd.lines.macd[0] > self.macd.lines.signal[0]):
                
                atr_value = self.atr[0]
                self.stop_loss = self.data.close[0] - (atr_value * self.p.atr_multiplier)
                self.take_profit = self.data.close[0] * (1 + self.p.take_profit_pct)
                
                cash = self.broker.get_cash()
                risk_amount = cash * self.p.risk_percent
                risk_per_unit = self.data.close[0] - self.stop_loss
                self.position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
                
                if self.position_size > 0:
                    self.buy(size=self.position_size)
                    self.entry_price = self.data.close[0]
                    self.highest_price = self.data.close[0]
        
        # 현재 포지션이 있을 때 (롱만)
        else:
            # Trailing Stop: 최고가 업데이트
            if self.data.close[0] > self.highest_price:
                self.highest_price = self.data.close[0]
                self.stop_loss = self.highest_price * (1 - self.p.trailing_stop_pct)
            
            # 청산 조건
            if self.data.close[0] < self.stop_loss:
                self.close()
            elif self.data.close[0] > self.take_profit:
                self.close()
            elif self.ema_short[0] < self.ema_long[0]:
                self.close()
