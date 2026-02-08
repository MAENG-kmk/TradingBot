import pandas as pd
import os
from datetime import datetime

from tools.getBolinger import getBolinger
from tools.getMa import getMACD
from tools.getAtr import getATR
from tools.checkRisk import checkRisk
from tools.getVolume import getVolume


class BacktestEngine:
    def __init__(self, initial_balance=100000, commission=0.0008, position_split=10):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.commission = commission
        self.position_split = position_split  # 10분할 or 20분할
        self.positions = {}
        self.trades = []
        self.logic_list = [getBolinger, getMACD]
        self.max_positions_held = 0
        
    def logic_filter(self, data):
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
        """분할 개수에 따른 포지션 크기"""
        return self.balance / self.position_split * 0.99
    
    def can_open_position(self):
        """새 포지션을 열 수 있는지 체크"""
        position_size = self.balance / self.position_split
        available = self.balance - sum(p['entry_value'] for p in self.positions.values())
        return available >= position_size
    
    def enter_position(self, symbol, current_price, data, current_time):
        if not checkRisk(data.copy()):
            return False
        if not getVolume(data.copy()):
            return False
        
        side = self.logic_filter(data)
        if side == 'None':
            return False
        
        if not self.can_open_position():
            return False
        
        atr = getATR(data.copy())
        target_ror = abs(atr / current_price) * 100
        
        if target_ror <= 5:
            target_ror = 5
            stop_loss = -2
        else:
            target_ror = target_ror
            stop_loss = -0.4 * target_ror
        
        position_value = self.calculate_position_size(symbol)
        amount = position_value / current_price
        
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
        
        self.max_positions_held = max(self.max_positions_held, len(self.positions))
        return True
    
    def check_exit(self, symbol, current_price, data, current_time):
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        
        if pos['side'] == 'long':
            ror = (current_price / pos['entry_price'] - 1) * 100
        else:
            ror = (1 - current_price / pos['entry_price']) * 100
        
        should_close = False
        
        if ror >= pos['target_ror']:
            should_close = True
            reason = f"Target hit ({ror:.2f}%)"
        elif ror < pos['stop_loss']:
            current_side = self.logic_filter(data)
            if current_side != pos['side']:
                should_close = True
                reason = f"Stop loss ({ror:.2f}%)"
        
        if should_close:
            exit_value = pos['amount'] * current_price
            exit_cost = exit_value * self.commission
            self.balance += exit_value - exit_cost
            
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
    
    def run_backtest(self, data_file, silent=True):
        df = pd.read_csv(f'backtestDatas/{data_file}')
        df['Date'] = pd.to_datetime(df['Date'])
        
        symbol = data_file.replace('.csv', '')
        
        if len(df) < 50:
            return
        
        for i in range(50, len(df)):
            current_data = df.iloc[:i+1].copy()
            current_price = float(current_data.iloc[-1]['Close'])
            current_time = current_data.iloc[-1]['Date']
            
            current_data = current_data.rename(columns={'Date': 'time'})
            current_data['High'] = pd.to_numeric(current_data['High'])
            current_data['Low'] = pd.to_numeric(current_data['Low'])
            current_data['Volume'] = pd.to_numeric(current_data['Volume'])
            
            if symbol in self.positions:
                self.check_exit(symbol, current_price, current_data, current_time)
            
            if symbol not in self.positions:
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
            del self.positions[symbol]
        
        if not silent:
            self.print_results()
    
    def print_results(self):
        print(f"\n{'='*60}")
        print("BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"Position Split: {self.position_split}개 분할")
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance: ${self.balance:,.2f}")
        
        total_return = (self.balance / self.initial_balance - 1) * 100
        print(f"Total Return: {total_return:.2f}%")
        
        if not self.trades:
            print("No trades executed")
            return
        
        print(f"\nTotal Trades: {len(self.trades)}")
        print(f"Max Positions Held: {self.max_positions_held}")
        
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
        
        # 최대 연속 손실 계산
        max_dd = self.calculate_max_drawdown()
        print(f"Max Drawdown: {max_dd:.2f}%")
    
    def calculate_max_drawdown(self):
        if not self.trades:
            return 0
        
        peak = self.initial_balance
        max_dd = 0
        
        for trade in self.trades:
            balance = trade['balance_after']
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd


def main():
    print("\n" + "="*70)
    print("포지션 분할 전략 비교: 10분할 vs 20분할")
    print("="*70)
    
    data_files = [
        'btcusdt_1h.csv',
        'btcusdt_4h.csv',
        'ethusdt_1h.csv',
        'ethusdt_4h.csv',
        'bchusdt_1h.csv',
        'bchusdt_4h.csv',
    ]
    
    results_10 = {}
    results_20 = {}
    
    print("\n[10분할 전략 테스트]")
    for data_file in data_files:
        if not os.path.exists(f'backtestDatas/{data_file}'):
            continue
        
        engine = BacktestEngine(initial_balance=100000, commission=0.0008, position_split=10)
        engine.run_backtest(data_file, silent=True)
        
        results_10[data_file] = {
            'final_balance': engine.balance,
            'return': (engine.balance / engine.initial_balance - 1) * 100,
            'trades': len(engine.trades),
            'win_rate': len([t for t in engine.trades if t['ror'] > 0]) / len(engine.trades) * 100 if engine.trades else 0,
            'max_dd': engine.calculate_max_drawdown(),
            'max_positions': engine.max_positions_held
        }
    
    print("\n[20분할 전략 테스트]")
    for data_file in data_files:
        if not os.path.exists(f'backtestDatas/{data_file}'):
            continue
        
        engine = BacktestEngine(initial_balance=100000, commission=0.0008, position_split=20)
        engine.run_backtest(data_file, silent=True)
        
        results_20[data_file] = {
            'final_balance': engine.balance,
            'return': (engine.balance / engine.initial_balance - 1) * 100,
            'trades': len(engine.trades),
            'win_rate': len([t for t in engine.trades if t['ror'] > 0]) / len(engine.trades) * 100 if engine.trades else 0,
            'max_dd': engine.calculate_max_drawdown(),
            'max_positions': engine.max_positions_held
        }
    
    # 비교 결과 출력
    print("\n" + "="*100)
    print(f"{'데이터':<25} | {'분할':<5} | {'수익률':>8} | {'거래수':>6} | {'승률':>7} | {'최대손실':>9} | {'최대포지션':>10}")
    print("="*100)
    
    for data_file in data_files:
        if data_file not in results_10:
            continue
        
        r10 = results_10[data_file]
        r20 = results_20[data_file]
        
        print(f"{data_file:<25} | 10개  | {r10['return']:>+7.2f}% | {r10['trades']:>6} | {r10['win_rate']:>6.1f}% | {r10['max_dd']:>8.2f}% | {r10['max_positions']:>10}")
        print(f"{'':<25} | 20개  | {r20['return']:>+7.2f}% | {r20['trades']:>6} | {r20['win_rate']:>6.1f}% | {r20['max_dd']:>8.2f}% | {r20['max_positions']:>10}")
        
        # 차이 표시
        return_diff = r20['return'] - r10['return']
        dd_diff = r20['max_dd'] - r10['max_dd']
        
        diff_symbol = "✅" if return_diff > 0 and dd_diff < 0 else "⚠️" if return_diff > 0 or dd_diff < 0 else "❌"
        print(f"{'':<25} | 차이  | {return_diff:>+7.2f}% | {r20['trades']-r10['trades']:>+6} | {r20['win_rate']-r10['win_rate']:>+6.1f}% | {dd_diff:>+8.2f}% | {diff_symbol}")
        print("-"*100)
    
    # 전체 평균
    print("\n" + "="*70)
    print("전체 평균 비교")
    print("="*70)
    
    avg_return_10 = sum(r['return'] for r in results_10.values()) / len(results_10)
    avg_return_20 = sum(r['return'] for r in results_20.values()) / len(results_20)
    avg_dd_10 = sum(r['max_dd'] for r in results_10.values()) / len(results_10)
    avg_dd_20 = sum(r['max_dd'] for r in results_20.values()) / len(results_20)
    avg_wr_10 = sum(r['win_rate'] for r in results_10.values()) / len(results_10)
    avg_wr_20 = sum(r['win_rate'] for r in results_20.values()) / len(results_20)
    
    print(f"10분할 - 평균 수익률: {avg_return_10:+.2f}% | 평균 최대손실: {avg_dd_10:.2f}% | 평균 승률: {avg_wr_10:.1f}%")
    print(f"20분할 - 평균 수익률: {avg_return_20:+.2f}% | 평균 최대손실: {avg_dd_20:.2f}% | 평균 승률: {avg_wr_20:.1f}%")
    print()
    print(f"수익률 차이: {avg_return_20 - avg_return_10:+.2f}%")
    print(f"리스크 차이: {avg_dd_20 - avg_dd_10:+.2f}%")
    
    if avg_return_20 > avg_return_10 and avg_dd_20 < avg_dd_10:
        print("\n✅ 결론: 20분할이 더 높은 수익률과 낮은 리스크를 제공합니다.")
    elif avg_return_20 > avg_return_10:
        print("\n⚠️ 결론: 20분할이 수익률은 높지만 리스크도 증가합니다.")
    elif avg_dd_20 < avg_dd_10:
        print("\n⚠️ 결론: 20분할이 리스크는 낮지만 수익률도 감소합니다.")
    else:
        print("\n❌ 결론: 10분할이 더 나은 성과를 보입니다.")


if __name__ == "__main__":
    main()
