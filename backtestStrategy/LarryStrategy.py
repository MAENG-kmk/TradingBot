import backtrader as bt
import numpy as np


class LarryStrategy(bt.Strategy):
    """
    Larry 변동성 돌파 양방향 전략
    
    롱:
    - 목표가(롱) = 오늘 시가 + (변동성 × 0.5)
    - 현재가 >= 목표가 시 매수
    - 손절: 어제 저가
    
    숏:
    - 목표가(숏) = 오늘 시가 - (변동성 × 0.5)
    - 현재가 <= 목표가 시 매도
    - 손절: 어제 고가
    """
    
    params = dict(
        k_factor=0.5,      # 변동성 배수 (0.5 = 50%)
        min_volatility_pct=0.009,  # 최소 변동성
        trailing_stop_pct=0.02,  # 트레일링 스탑 (2%)
    )
    
    def __init__(self):
        # 거래 정보
        self.entry_price = 0
        self.stop_loss = 0
        self.highest_price = 0
        self.lowest_price = 0
        self.target_price = 0
    
    def next(self):
        # 이전 데이터가 충분하지 않으면 건너뛰기
        if len(self) < 2:
            return
        
        # 이전 캔들의 고가/저가
        prev_high = self.data.high[-1]
        prev_low = self.data.low[-1]
        volatility = prev_high - prev_low
        
        # 최소 변동성 체크
        min_vol = self.data.open[0] * self.p.min_volatility_pct
        
        # 현재 포지션이 없을 때 (진입)
        if not self.position:
            # ===== 롱 진입 =====
            if volatility >= min_vol:
                target_long = self.data.open[0] + (volatility * self.p.k_factor)
                
                # 현재가가 목표가 이상이면 매수
                if self.data.close[0] >= target_long:
                    self.target_price = target_long
                    self.stop_loss = prev_low
                    
                    # 포지션 크기 계산
                    risk_amount = self.broker.get_cash() * 0.02  # 2% 리스크
                    risk_per_unit = self.data.close[0] - self.stop_loss
                    
                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                        if position_size > 0:
                            self.buy(size=position_size)
                            self.entry_price = self.data.close[0]
                            self.highest_price = self.data.close[0]
                            self.lowest_price = self.data.close[0]
            
            # ===== 숏 진입 =====
            if volatility >= min_vol:
                target_short = self.data.open[0] - (volatility * self.p.k_factor)
                
                # 현재가가 목표가 이하면 매도
                if self.data.close[0] <= target_short:
                    self.target_price = target_short
                    self.stop_loss = prev_high
                    
                    # 포지션 크기 계산
                    risk_amount = self.broker.get_cash() * 0.02  # 2% 리스크
                    risk_per_unit = self.stop_loss - self.data.close[0]
                    
                    if risk_per_unit > 0:
                        position_size = risk_amount / risk_per_unit
                        if position_size > 0:
                            self.sell(size=position_size)
                            self.entry_price = self.data.close[0]
                            self.highest_price = self.data.close[0]
                            self.lowest_price = self.data.close[0]
        
        # 현재 포지션이 있을 때 (청산)
        else:
            # 롱 포지션
            if self.position.size > 0:
                # Trailing Stop: 최고가 업데이트
                if self.data.close[0] > self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = self.highest_price * (1 - self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] < self.stop_loss:
                    self.close()
            
            # 숏 포지션
            elif self.position.size < 0:
                # Trailing Stop: 최저가 업데이트
                if self.data.close[0] < self.lowest_price:
                    self.lowest_price = self.data.close[0]
                    self.stop_loss = self.lowest_price * (1 + self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] > self.stop_loss:
                    self.close()
