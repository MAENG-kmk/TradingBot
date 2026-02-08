import backtrader as bt
import numpy as np


class SDE_OnlyStrategy(bt.Strategy):
    """
    SDE (확률미분방정식) 기반 순수 전략
    - GBM 변동성 계산
    - Monte Carlo 시뮬레이션으로 가격 범위 예측
    - 극단값(5%, 95% percentile)에서만 진입
    - 변동성 기반 동적 손절
    """
    params = dict(
        sde_window=20,
        sde_percentile_lower=20,  # 5 → 20 (더 완화)
        sde_percentile_upper=80,  # 95 → 80 (더 완화)
        sde_num_sims=500,
        atr_period=14,
        atr_multiplier=2.0,
        take_profit_pct=0.05,
        risk_percent=0.02,
        trailing_stop_pct=0.02,
    )

    def __init__(self):
        # 지표 설정
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        
        # SDE 기반 변동성 추적
        self.returns_buffer = []
        self.volatility = 0.02
        self.sde_lower_bound = 0
        self.sde_upper_bound = 0
        
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
            
            if len(self.returns_buffer) > self.p.sde_window:
                self.returns_buffer.pop(0)
            
            if len(self.returns_buffer) > 5:
                self.volatility = np.std(self.returns_buffer) * np.sqrt(252)
        
        # ===== Monte Carlo GBM 시뮬레이션 =====
        if len(self.data) > 30:
            self.calculate_sde_bounds()
        
        # 현재 포지션이 없을 때
        if not self.position:
            # ===== 롱 진입: SDE 하단 극단값 =====
            if self.data.close[0] < self.sde_lower_bound:
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
                    print(f"[BUY] {self.data.datetime.date(0)} | Price: {self.entry_price:.2f} | SDE Lower: {self.sde_lower_bound:.2f}")
            
            # ===== 숏 진입: SDE 상단 극단값 =====
            elif self.data.close[0] > self.sde_upper_bound:
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
                    print(f"[SELL] {self.data.datetime.date(0)} | Price: {self.entry_price:.2f} | SDE Upper: {self.sde_upper_bound:.2f}")
        
        # 현재 포지션이 있을 때
        else:
            if self.position.size > 0:  # 롱 포지션
                # Trailing Stop
                if self.data.close[0] > self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = self.highest_price * (1 - self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] < self.stop_loss:
                    print(f"[CLOSE-SL] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
                elif self.data.close[0] > self.take_profit:
                    print(f"[CLOSE-TP] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
                elif self.data.close[0] > (self.sde_lower_bound + self.sde_upper_bound) / 2:
                    print(f"[CLOSE-MR] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
            
            else:  # 숏 포지션
                # Trailing Stop
                if self.data.close[0] < self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = self.highest_price * (1 + self.p.trailing_stop_pct)
                
                # 청산 조건
                if self.data.close[0] > self.stop_loss:
                    print(f"[CLOSE-SL] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
                elif self.data.close[0] < self.take_profit:
                    print(f"[CLOSE-TP] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
                elif self.data.close[0] < (self.sde_lower_bound + self.sde_upper_bound) / 2:
                    print(f"[CLOSE-MR] {self.data.datetime.date(0)} | Price: {self.data.close[0]:.2f}")
                    self.close()
    
    def calculate_sde_bounds(self):
        """
        GBM 기반 Monte Carlo 시뮬레이션으로 가격 범위 계산
        """
        # 충분한 데이터가 없으면 계산 안 함
        if len(self.returns_buffer) < 5:
            return
        
        current_price = self.data.close[0]
        mean_return = np.mean(self.returns_buffer)
        
        # 0 보다 큰 volatility만 사용
        if self.volatility <= 0:
            self.volatility = 0.02
        
        # Monte Carlo 시뮬레이션
        num_sims = self.p.sde_num_sims
        dt = 1 / 252
        
        simulated_prices = np.zeros(num_sims)
        
        for i in range(num_sims):
            dW = np.random.normal(0, np.sqrt(dt))
            price = current_price * np.exp(
                (mean_return - 0.5 * self.volatility**2) * dt + 
                self.volatility * dW
            )
            # 음수 가격 방지
            simulated_prices[i] = max(price, current_price * 0.5)
        
        # Percentile 범위 계산
        lower = np.percentile(simulated_prices, self.p.sde_percentile_lower)
        upper = np.percentile(simulated_prices, self.p.sde_percentile_upper)
        
        # 이상한 값 방지
        if lower > 0 and upper > lower:
            self.sde_lower_bound = lower
            self.sde_upper_bound = upper
        else:
            # 계산 실패 시 기본값 설정
            self.sde_lower_bound = current_price * 0.95
            self.sde_upper_bound = current_price * 1.05
