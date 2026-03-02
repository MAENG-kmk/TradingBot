"""
ETH 자동매매 전략 (OptimizedStrategy 기반)

백테스트 기반 성능:
- RSI 80/20 (극단값)
- EMA 10/30
- MACD 필터
- ATR 기반 손절매
- Trailing Stop
- ROR: +91.71% (ETH 4H, 백테스트)
- Sharpe: 0.64, MDD: 25.85%

사용법:
  python eth_auto_trader.py
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime
from SecretVariables import BINANCE_API_KEY, BINANCE_API_SECRET
from binance.client import Client
from tools.BetController import BetController
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.getData import get4HData
from tools.setLeverage import setLeverage
from tools.createOrder import createOrder
from tools.trendFilter import checkTrendStrength
import time
import asyncio

client = Client(api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET)


class ETHAutoTrader:
    """ETH 자동매매 전략 (OptimizedStrategy)"""
    
    def __init__(self):
        """초기화"""
        self.symbol = "ETHUSDT"
        
        # 전략 파라미터 (백테스트 최적값)
        self.ema_short = 10
        self.ema_long = 30
        self.rsi_period = 14
        self.rsi_overbuy = 80     # 극단값
        self.rsi_oversell = 20    # 극단값
        self.atr_period = 14
        self.atr_multiplier = 2.2
        self.take_profit_pct = 0.07  # 7%
        self.risk_percent = 0.02   # 거래당 2% 리스크
        self.trailing_stop_pct = 0.02  # 2%
        
        # 거래 정보
        self.position_info = {}  # {symbol: [side, entry_price, tp, sl, quantity]}
        self.highest_price = {}
        
        # 베팅 컨트롤러
        logic_list = []
        self.bet_controller = BetController(client, logic_list)
    
    def calculate_atr(self, klines):
        """
        ATR 계산 (현재 값만)
        
        Args:
            klines: Binance 4시간 캔들 데이터
        
        Returns:
            float: ATR 값
        """
        try:
            if len(klines) < self.atr_period:
                return 0
            
            highs = np.array([float(k[2]) for k in klines[-self.atr_period:]])
            lows = np.array([float(k[3]) for k in klines[-self.atr_period:]])
            closes = np.array([float(k[4]) for k in klines[-self.atr_period:]])
            
            tr = np.maximum(
                np.maximum(highs - lows, abs(highs - np.roll(closes, 1))),
                abs(lows - np.roll(closes, 1))
            )
            
            atr = np.mean(tr)
            return atr
        except Exception as e:
            print(f"❌ ATR 계산 실패: {e}")
            return 0
    
    def calculate_ema(self, prices, period):
        """
        EMA 계산
        
        Args:
            prices: 가격 배열
            period: EMA 기간
        
        Returns:
            float: 현재 EMA 값
        """
        try:
            if len(prices) < period:
                return prices[-1]
            
            df = pd.Series(prices)
            ema = df.ewm(span=period, adjust=False).mean()
            return float(ema.iloc[-1])
        except Exception as e:
            print(f"❌ EMA 계산 실패: {e}")
            return prices[-1] if prices else 0
    
    def calculate_rsi(self, prices, period=14):
        """
        RSI 계산
        
        Args:
            prices: 가격 배열
            period: RSI 기간
        
        Returns:
            float: RSI 값
        """
        try:
            if len(prices) < period + 1:
                return 50
            
            df = pd.Series(prices)
            delta = df.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1])
        except Exception as e:
            print(f"❌ RSI 계산 실패: {e}")
            return 50
    
    def calculate_macd(self, prices):
        """
        MACD 계산
        
        Args:
            prices: 가격 배열
        
        Returns:
            tuple: (macd, signal) 또는 (None, None)
        """
        try:
            if len(prices) < 26:
                return None, None
            
            df = pd.Series(prices)
            ema12 = df.ewm(span=12, adjust=False).mean()
            ema26 = df.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            
            return float(macd.iloc[-1]), float(signal.iloc[-1])
        except Exception as e:
            print(f"❌ MACD 계산 실패: {e}")
            return None, None
    
    def check_signal(self, df):
        """
        매매 신호 확인
        
        Args:
            df: 4시간 캔들 DataFrame (index: time, columns: Open, High, Low, Close, Volume, Body)
        
        Returns:
            tuple: (signal_type, signal_data)
                signal_type: 'BUY', 'SELL', None
                signal_data: 신호 정보 dict
        """
        try:
            if len(df) < 50:
                return None, None
            
            # 가격 데이터 추출
            closes = df['Close'].values
            current_price = closes[-1]
            
            # 지표 계산
            ema_short = self.calculate_ema(closes, self.ema_short)
            ema_long = self.calculate_ema(closes, self.ema_long)
            rsi = self.calculate_rsi(closes, self.rsi_period)
            macd, signal_line = self.calculate_macd(closes)
            
            # ATR 계산 (klines 형식으로 변환)
            klines = []
            for i in range(len(df)):
                row = df.iloc[i]
                klines.append([
                    None,  # 0: time (사용 안 함)
                    row['Open'],  # 1: open
                    row['High'],  # 2: high
                    row['Low'],   # 3: low
                    row['Close'], # 4: close
                ])
            atr = self.calculate_atr(klines)
            
            # ===== 롱 신호 (진입) =====
            # 횡보장 필터: 방향성 없으면 진입 금지
            if (ema_short > ema_long and
                rsi < self.rsi_overbuy and
                rsi > self.rsi_oversell and
                macd is not None and
                macd > signal_line and
                checkTrendStrength(df)):
                
                stop_loss = current_price - (atr * self.atr_multiplier)
                take_profit = current_price * (1 + self.take_profit_pct)
                
                return 'BUY', {
                    'price': current_price,
                    'ema_short': ema_short,
                    'ema_long': ema_long,
                    'rsi': rsi,
                    'macd': macd,
                    'signal': signal_line,
                    'atr': atr,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit
                }
            
            # ===== 청산 신호 (보유 중일 때) =====
            if self.symbol in self.position_info:
                side, entry_price, tp, sl, qty = self.position_info[self.symbol]
                
                # 익절
                if current_price >= tp:
                    return 'CLOSE', {
                        'reason': 'Take Profit',
                        'price': current_price,
                        'entry': entry_price,
                        'profit_pct': ((current_price - entry_price) / entry_price) * 100
                    }
                
                # 손절
                if current_price <= sl:
                    return 'CLOSE', {
                        'reason': 'Stop Loss',
                        'price': current_price,
                        'entry': entry_price,
                        'profit_pct': ((current_price - entry_price) / entry_price) * 100
                    }
                
                # Trailing Stop
                if current_price > self.highest_price.get(self.symbol, entry_price):
                    self.highest_price[self.symbol] = current_price
                    new_sl = current_price * (1 - self.trailing_stop_pct)
                    self.position_info[self.symbol][3] = new_sl
                
                if current_price <= self.position_info[self.symbol][3]:
                    return 'CLOSE', {
                        'reason': 'Trailing Stop',
                        'price': current_price,
                        'entry': entry_price,
                        'profit_pct': ((current_price - entry_price) / entry_price) * 100
                    }
                
                # EMA 교차 (탈출)
                if ema_short < ema_long:
                    return 'CLOSE', {
                        'reason': 'EMA Crossover',
                        'price': current_price,
                        'entry': entry_price,
                        'profit_pct': ((current_price - entry_price) / entry_price) * 100
                    }
            
            return None, None
        
        except Exception as e:
            print(f"❌ 신호 확인 실패: {e}")
            return None, None
    
    def execute_trade(self, signal_type, signal_data):
        """
        거래 실행
        
        Args:
            signal_type: 'BUY' or 'CLOSE'
            signal_data: 신호 데이터
        """
        try:
            total_balance, available_balance = getBalance(client)
            
            if signal_type == 'BUY':
                # 이미 포지션이 있으면 진입하지 않음
                if self.symbol in self.position_info:
                    print(f"⏭️  {self.symbol} 이미 포지션 있음")
                    return
                
                # 주문 수량 계산
                bullet = available_balance * 0.99  # 가용 자산의 50%
                current_price = signal_data['price']
                amount = math.floor((bullet / current_price) * 100) / 100
                
                if amount < 0.001:
                    print(f"⏭️  주문량 너무 적음: {amount}")
                    return
                
                # 레버리지 설정 (1배: 현물처럼)
                setLeverage(client, self.symbol, 1)
                
                # 주문 생성
                response = createOrder(client, self.symbol, 'BUY', 'MARKET', amount)
                
                if response:
                    # 포지션 정보 저장 (수량 포함)
                    self.position_info[self.symbol] = [
                        'LONG',
                        current_price,
                        signal_data['take_profit'],
                        signal_data['stop_loss'],
                        amount  # 청산할 때 필요한 수량
                    ]
                    self.highest_price[self.symbol] = current_price
                    self.bet_controller.saveNew(self.symbol, 5)
                    
                    msg = f"\n✅ ETH 매수 성공\n"
                    msg += f"   가격: ${current_price:.2f}\n"
                    msg += f"   수량: {amount}\n"
                    msg += f"   목표가: ${signal_data['take_profit']:.2f}\n"
                    msg += f"   손절가: ${signal_data['stop_loss']:.2f}\n"
                    msg += f"   RSI: {signal_data['rsi']:.1f}\n"
                    msg += f"   EMA: {signal_data['ema_short']:.1f} / {signal_data['ema_long']:.1f}"
                    print(msg)
                    asyncio.run(send_message(msg))
                else:
                    print(f"❌ 주문 실패")
            
            elif signal_type == 'CLOSE':
                if self.symbol not in self.position_info:
                    return
                
                # 저장된 수량으로 청산
                position = self.position_info[self.symbol]
                close_quantity = position[4]  # 진입 시 저장한 수량
                
                response = createOrder(client, self.symbol, 'SELL', 'MARKET', close_quantity)
                
                if response:
                    entry_price = signal_data['entry']
                    close_price = signal_data['price']
                    profit_pct = signal_data['profit_pct']
                    
                    msg = f"\n✅ ETH 매도 성공 ({signal_data['reason']})\n"
                    msg += f"   진입가: ${entry_price:.2f}\n"
                    msg += f"   청산가: ${close_price:.2f}\n"
                    msg += f"   수익률: {profit_pct:.2f}%"
                    print(msg)
                    asyncio.run(send_message(msg))
                    
                    # 포지션 정보 삭제
                    del self.position_info[self.symbol]
                    if self.symbol in self.highest_price:
                        del self.highest_price[self.symbol]
                else:
                    print(f"❌ 청산 실패")
        
        except Exception as e:
            print(f"❌ 거래 실행 실패: {e}")
    
    def run(self):
        """메인 루프 - 4시간마다 체크"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ETH 자동매매 체크")
        
        try:
            # 4시간 데이터 가져오기 (최근 100개 캔들)
            df = get4HData(client, self.symbol, limit=100)
            
            if df is None or len(df) < 50:
                print("❌ 충분한 데이터 없음")
                return
            
            # 신호 확인
            signal_type, signal_data = self.check_signal(df)
            
            if signal_type:
                print(f"📊 신호 감지: {signal_type}")
                self.execute_trade(signal_type, signal_data)
            else:
                # 대기 중일 때만 상태 출력
                if self.symbol not in self.position_info:
                    print("⏸️  신호 없음 (대기 중)")
                else:
                    side, entry, tp, sl, qty = self.position_info[self.symbol]
                    print(f"📍 포지션 유지 중: Qty {qty}, Entry ${entry:.2f}, TP ${tp:.2f}, SL ${sl:.2f}")
        
        except Exception as e:
            print(f"❌ 오류 발생: {e}")


def main():
    """메인 함수"""
    trader = ETHAutoTrader()
    
    print("=" * 60)
    print("ETH 자동매매 시작")
    print("=" * 60)
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"전략: OptimizedStrategy (RSI 80/20, EMA 10/30, MACD)")
    print("=" * 60)
    
    try:
        # 5분마다 체크 (4시간 봉 확인)
        while True:
            trader.run()
            time.sleep(300)  # 5분 대기
    
    except KeyboardInterrupt:
        print("\n\n자동매매 종료 (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ 치명적 오류: {e}")
        asyncio.run(send_message(f"❌ ETH 자동매매 오류: {e}"))


if __name__ == "__main__":
    main()
