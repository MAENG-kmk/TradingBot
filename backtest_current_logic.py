import pandas as pd
import os
from datetime import datetime

# 현재 로직 import
from tools.getBolinger import getBolinger
from tools.getMa import getMACD
from tools.getAtr import getATR
from tools.checkRisk import checkRisk
from tools.getVolume import getVolume


class BacktestEngine:
    def __init__(self, initial_balance=100000, commission=0.0008):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.commission = commission
        self.positions = {}  # {symbol: {'side': 'long'/'short', 'entry_price': float, 'amount': float, 'target': float, 'stop': float}}
        self.trades = []
        self.logic_list = [getBolinger, getMACD]
        
    def logic_filter(self, data):
        """enterPosition.py의 logic_filter 재현"""
        result = 'None'
        for logic in self.logic_list:
            side = logic(data.copy())
            if side == 'None':
                break
            if side == result:
                continue
            elif result == 'None':
                result = side
            else:
                result = 'None'
                break
        return result
    
    def calculate_position_size(self, symbol):
        """전체 잔고의 10% 투자"""
        return self.balance * 0.1
    
    def enter_position(self, symbol, current_price, data, current_time):
        """포지션 진입"""
        # 리스크 체크
        if not checkRisk(data.copy()):
            return False
        
        # 볼륨 체크
        if not getVolume(data.copy()):
            return False
        
        # 로직 필터
        side = self.logic_filter(data)
        if side == 'None':
            return False
        
        # ATR 기반 목표 수익률 계산
        atr = getATR(data.copy())
        target_ror = abs(atr / current_price) * 100
        
        # BetController 로직 재현
        if target_ror <= 8:
            target_ror = 8
            stop_loss = -3.5
        else:
            target_ror = target_ror
            stop_loss = -0.4 * target_ror
        
        # 포지션 크기 계산
        position_value = self.calculate_position_size(symbol)
        amount = position_value / current_price
        
        # 수수료 차감
        entry_cost = position_value * (1 + self.commission)
        if entry_cost > self.balance:
            return False
        
        self.balance -= entry_cost
        
        self.positions[symbol] = {
            'side': side,
            'entry_price': current_price,
            'entry_value': position_value,
            'amount': amount,
            'target_ror': target_ror,
            'stop_loss': stop_loss,
            'entry_time': current_time
        }
        
        return True
    
    def check_exit(self, symbol, current_price, data, current_time):
        """포지션 청산 체크"""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        
        # 현재 수익률 계산
        if pos['side'] == 'long':
            ror = (current_price / pos['entry_price'] - 1) * 100
        else:  # short
            ror = (1 - current_price / pos['entry_price']) * 100
        
        should_close = False
        
        # 목표 수익률 달성
        if ror >= pos['target_ror']:
            should_close = True
            reason = f"Target hit ({ror:.2f}%)"
        
        # 손절
        elif ror < pos['stop_loss']:
            # BetController의 decideGoOrStop 로직
            current_side = self.logic_filter(data)
            if current_side != pos['side']:
                should_close = True
                reason = f"Stop loss ({ror:.2f}%)"
        
        if should_close:
            # 청산 실행
            exit_value = pos['amount'] * current_price
            exit_cost = exit_value * self.commission
            self.balance += exit_value - exit_cost
            
            profit = self.balance - (self.initial_balance if not self.trades else self.trades[-1]['balance_after'])
            
            self.trades.append({
                'symbol': symbol,
                'side': pos['side'],
                'entry_price': pos['entry_price'],
                'exit_price': current_price,
                'entry_time': pos['entry_time'],
                'exit_time': current_time,
                'ror': ror,
                'profit': exit_value - pos['entry_value'] - (pos['entry_value'] * self.commission) - exit_cost,
                'balance_after': self.balance,
                'reason': reason
            })
            
            del self.positions[symbol]
            return True
        
        return False
    
    def run_backtest(self, data_file):
        """백테스트 실행"""
        print(f"\n{'='*60}")
        print(f"Backtesting: {data_file}")
        print(f"{'='*60}")
        
        # 데이터 로드
        df = pd.read_csv(f'backtestDatas/{data_file}')
        df['Date'] = pd.to_datetime(df['Date'])
        
        symbol = data_file.replace('.csv', '')
        
        # 최소 50개 데이터 필요
        if len(df) < 50:
            print("Not enough data")
            return
        
        # 백테스트 실행
        for i in range(50, len(df)):
            current_data = df.iloc[:i+1].copy()
            current_price = float(current_data.iloc[-1]['Close'])
            current_time = current_data.iloc[-1]['Date']
            
            # 데이터프레임 컬럼명 통일 (tools 함수들이 기대하는 형식)
            current_data = current_data.rename(columns={'Date': 'time'})
            current_data['High'] = pd.to_numeric(current_data['High'])
            current_data['Low'] = pd.to_numeric(current_data['Low'])
            current_data['Volume'] = pd.to_numeric(current_data['Volume'])
            
            # 기존 포지션 체크 (청산)
            if symbol in self.positions:
                self.check_exit(symbol, current_price, current_data, current_time)
            
            # 새 포지션 진입 (포지션이 없을 때만)
            if symbol not in self.positions and self.balance > self.initial_balance * 0.1:
                self.enter_position(symbol, current_price, current_data, current_time)
        
        # 마지막 포지션 강제 청산
        if symbol in self.positions:
            pos = self.positions[symbol]
            current_price = float(df.iloc[-1]['Close'])
            exit_value = pos['amount'] * current_price
            self.balance += exit_value * (1 - self.commission)
            
            if pos['side'] == 'long':
                ror = (current_price / pos['entry_price'] - 1) * 100
            else:
                ror = (1 - current_price / pos['entry_price']) * 100
            
            self.trades.append({
                'symbol': symbol,
                'side': pos['side'],
                'entry_price': pos['entry_price'],
                'exit_price': current_price,
                'entry_time': pos['entry_time'],
                'exit_time': df.iloc[-1]['Date'],
                'ror': ror,
                'profit': exit_value - pos['entry_value'],
                'balance_after': self.balance,
                'reason': 'Force close'
            })
        
        # 결과 출력
        self.print_results()
    
    def print_results(self):
        """백테스트 결과 출력"""
        print(f"\n{'='*60}")
        print("BACKTEST RESULTS")
        print(f"{'='*60}")
        
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance: ${self.balance:,.2f}")
        
        total_return = (self.balance / self.initial_balance - 1) * 100
        print(f"Total Return: {total_return:.2f}%")
        
        if not self.trades:
            print("No trades executed")
            return
        
        print(f"\nTotal Trades: {len(self.trades)}")
        
        winning_trades = [t for t in self.trades if t['ror'] > 0]
        losing_trades = [t for t in self.trades if t['ror'] <= 0]
        
        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0
        print(f"Win Rate: {win_rate:.2f}% ({len(winning_trades)}/{len(self.trades)})")
        
        if winning_trades:
            avg_win = sum(t['ror'] for t in winning_trades) / len(winning_trades)
            print(f"Average Win: {avg_win:.2f}%")
        
        if losing_trades:
            avg_loss = sum(t['ror'] for t in losing_trades) / len(losing_trades)
            print(f"Average Loss: {avg_loss:.2f}%")
        
        total_commission = sum(t['profit'] for t in self.trades)
        print(f"Total Commission Impact: ${total_commission:.2f}")
        
        print(f"\n{'='*60}")
        print("TRADE HISTORY (Last 10)")
        print(f"{'='*60}")
        
        for trade in self.trades[-10:]:
            print(f"{trade['entry_time']} -> {trade['exit_time']}")
            print(f"  {trade['side'].upper()}: ${trade['entry_price']:.2f} -> ${trade['exit_price']:.2f}")
            print(f"  RoR: {trade['ror']:+.2f}% | Profit: ${trade['profit']:+,.2f} | {trade['reason']}")
            print(f"  Balance: ${trade['balance_after']:,.2f}")
            print()


def main():
    """모든 데이터 파일에 대해 백테스트 실행"""
    data_files = [
        'btcusdt_1h.csv',
        'btcusdt_4h.csv',
        'ethusdt_1h.csv',
        'ethusdt_4h.csv',
        'bchusdt_1h.csv',
        'bchusdt_4h.csv',
    ]
    
    print("\n" + "="*60)
    print("현재 로직 백테스트 (Bollinger + MACD)")
    print("설정: 5% 익절 / -2% 손절 / 수수료 0.08%")
    print("="*60)
    
    results = {}
    
    for data_file in data_files:
        if not os.path.exists(f'backtestDatas/{data_file}'):
            print(f"Skipping {data_file} (not found)")
            continue
        
        engine = BacktestEngine(initial_balance=100000, commission=0.0008)
        engine.run_backtest(data_file)
        
        results[data_file] = {
            'final_balance': engine.balance,
            'return': (engine.balance / engine.initial_balance - 1) * 100,
            'trades': len(engine.trades),
            'win_rate': len([t for t in engine.trades if t['ror'] > 0]) / len(engine.trades) * 100 if engine.trades else 0
        }
    
    # 전체 요약
    print("\n" + "="*60)
    print("SUMMARY OF ALL BACKTESTS")
    print("="*60)
    
    for file, result in results.items():
        print(f"{file:25} | Return: {result['return']:+7.2f}% | Trades: {result['trades']:3} | Win Rate: {result['win_rate']:5.1f}%")


if __name__ == "__main__":
    main()
