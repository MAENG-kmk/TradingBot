import backtrader as bt
import numpy as np


class MeanReversionStrategy(bt.Strategy):
    """
    평균회귀(Mean Reversion) 전략
    - 가격이 평균에서 극단적으로 벗어났을 때 진입
    - 가격이 평균으로 돌아올 때 청산
    - 거래 빈도 낮음, 거래당 수익 높음
    """
    params = dict(
        bb_period=20,           # Bollinger Bands 기간
        bb_devfactor=2.0,       # BB 표준편차 배수
        rsi_period=14,          # RSI 기간
        rsi_oversold=25,        # RSI 과매도 (극단값)
        rsi_overbought=75,      # RSI 과매수 (극단값)
        atr_period=14,          # ATR 기간
        atr_multiplier=1.5,     # 손절 거리
        take_profit_pct=0.04,   # 익절: 4% (중간값으로 돌아올 것 기대)
        risk_percent=0.03,      # 거래당 3% 리스크
        trailing_stop_pct=0.025,
    )

    def __init__(self):
        # 지표 설정
        self.bb = bt.ind.BollingerBands(self.data.close, period=self.p.bb_period, devfactor=self.p.bb_devfactor)
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        
        # SDE 기반 변동성
        self.returns_buffer = []
        self.volatility = 0.02
        
        # 거래 정보
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.position_size = 0
        self.highest_price = 0

    def next(self):
        # ===== GBM 기반 변동성 계산 =====
        if len(self.data) > 1:
            ret = (self.data.close[0] - self.data.close[-1]) / self.data.close[-1]
            self.returns_buffer.append(ret)
            
            if len(self.returns_buffer) > 20:
                self.returns_buffer.pop(0)
            
            if len(self.returns_buffer) > 5:
                self.volatility = np.std(self.returns_buffer) * np.sqrt(252)
        
        # 현재 포지션이 없을 때
        if not self.position:
            # ===== 롱 진입: 극도로 과매도 상태 =====
            # 가격이 BB 하단 근처 + RSI < 25 (극단적 과매도)
            if (self.data.close[0] < self.bb.lines.bot[0] * 1.02 and  # BB 하단에서 2% 위
                self.rsi[0] < self.p.rsi_oversold):
                
                atr_value = self.atr[0]
                sde_stop_distance = atr_value * self.p.atr_multiplier * (1 + self.volatility)
                self.stop_loss = self.data.close[0] - sde_stop_distance
                self.take_profit = self.data.close[0] * (1 + self.p.take_profit_pct)
                
                cash = self.broker.get_cash()
                risk_amount = cash * self.p.risk_percent
                risk_per_unit = self.data.close[0] - self.stop_loss
                self.position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
                
                if self.position_size > 0:
                    self.buy(size=self.position_size)
                    self.entry_price = self.data.close[0]
                    self.highest_price = self.data.close[0]
            
            # ===== 숏 진입: 극도로 과매수 상태 =====
            # 가격이 BB 상단 근처 + RSI > 75 (극단적 과매수)
            elif (self.data.close[0] > self.bb.lines.top[0] * 0.98 and  # BB 상단에서 2% 아래
                  self.rsi[0] > self.p.rsi_overbought):
                
                atr_value = self.atr[0]
                sde_stop_distance = atr_value * self.p.atr_multiplier * (1 + self.volatility)
                self.stop_loss = self.data.close[0] + sde_stop_distance
                self.take_profit = self.data.close[0] * (1 - self.p.take_profit_pct)
                
                cash = self.broker.get_cash()
                risk_amount = cash * self.p.risk_percent
                risk_per_unit = self.stop_loss - self.data.close[0]
                self.position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
                
                if self.position_size > 0:
                    self.sell(size=self.position_size)
                    self.entry_price = self.data.close[0]
                    self.highest_price = self.data.close[0]
        
        # 현재 포지션이 있을 때
        else:
            if self.position.size > 0:  # 롱 포지션
                # Trailing Stop
                if self.data.close[0] > self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = self.highest_price * (1 - self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] < self.stop_loss:
                    self.close()
                elif self.data.close[0] > self.take_profit:
                    self.close()
                # 평균으로의 회귀 (BB 중간선 터치 또는 RSI 정상화)
                elif self.data.close[0] > self.bb.lines.mid[0]:
                    self.close()
            
            else:  # 숏 포지션
                # Trailing Stop
                if self.data.close[0] < self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = self.highest_price * (1 + self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] > self.stop_loss:
                    self.close()
                elif self.data.close[0] < self.take_profit:
                    self.close()
                # 평균으로의 회귀
                elif self.data.close[0] < self.bb.lines.mid[0]:
                    self.close()
