"""
BTC 5분봉 고빈도 단타 전략 백테스트

전략: 볼린저밴드 돌파 + RSI 모멘텀 + 거래량 확인 스캘핑

진입 조건:
  롱: 종가 > BB 상단 + RSI(7) 50~75 + 거래량 > MA × vol_mult
  숏: 종가 < BB 하단 + RSI(7) 25~50 + 거래량 > MA × vol_mult

청산 조건 (우선순위):
  1. 하드스탑: 고가/저가가 진입가 ∓ ATR × stop_mult 터치
  2. 목표가:   고가/저가가 진입가 ± ATR × target_mult 터치
  3. 시간청산: time_exit_bars 봉 초과

사용법:
  python backtest_hft.py
"""

import sys
import os
sys.path.append(os.path.abspath("."))

import backtrader as bt
import numpy as np


class HFTStrategy(bt.Strategy):
    """
    5분봉 RSI 극단값 평균회귀 스캘핑

    진입 조건:
      - RSI(3) < rsi_oversold  → 롱 (극단적 과매도)
      - RSI(3) > rsi_overbought → 숏 (극단적 과매수)
      - BB 위치 확인: 롱은 BB 하단 이하, 숏은 BB 상단 이상
      - ADX < adx_max: 강한 추세 구간 제외 (평균회귀가 잘 안 됨)

    청산 조건:
      - 목표: ATR × target_mult (빠른 회귀 포착)
      - 손절: ATR × stop_mult
      - 시간: time_exit_bars 봉 초과
    """
    params = dict(
        # RSI 극단값 기준
        rsi_period    = 3,
        rsi_oversold  = 10,
        rsi_overbought= 90,
        # BB 필터 (과매도가 BB 하단 이하인지 확인)
        bb_period     = 20,
        bb_std        = 2.0,
        # ADX 상한 (강한 추세에서는 평균회귀 진입 금지)
        adx_period    = 14,
        adx_max       = 30,
        # ATR 청산
        atr_period    = 7,
        stop_mult     = 2.0,   # 손절폭
        target_mult   = 1.0,   # 목표 (빠른 회귀, 고승률)
        # 시간 청산 (12봉 = 60분)
        time_exit_bars= 12,
        # 포지션 크기
        position_pct  = 0.99,
    )

    def __init__(self):
        self.rsi  = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr  = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.dmi  = bt.ind.DirectionalMovementIndex(self.data, period=self.p.adx_period)
        self._pending_dir = None
        self._reset()

    def _reset(self):
        self.entry_price  = 0.0
        self.stop_price   = 0.0
        self.target_price = 0.0
        self.bars_held    = 0
        self.entry_atr    = 0.0

    def _bb(self):
        period = self.p.bb_period
        if len(self.data) < period:
            return None, None
        closes = np.array([self.data.close[-i] for i in range(period-1, -1, -1)], dtype=float)
        mid = closes.mean()
        std = closes.std()
        return mid + self.p.bb_std * std, mid - self.p.bb_std * std

    def notify_order(self, order):
        if order.status == order.Completed and self._pending_dir is not None:
            fill = order.executed.price
            atr  = self.entry_atr
            if self._pending_dir == 'long':
                self.stop_price   = fill - atr * self.p.stop_mult
                self.target_price = fill + atr * self.p.target_mult
            else:
                self.stop_price   = fill + atr * self.p.stop_mult
                self.target_price = fill - atr * self.p.target_mult
            self.entry_price  = fill
            self.bars_held    = 0
            self._pending_dir = None
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._pending_dir = None

    def next(self):
        bb_upper, bb_lower = self._bb()
        if bb_upper is None:
            return

        rsi   = self.rsi[0]
        atr   = self.atr[0]
        adx   = self.dmi.adx[0]
        price = self.data.close[0]

        # ── 진입 ──────────────────────────────────────────
        if not self.position and self._pending_dir is None:
            weak_trend = adx < self.p.adx_max  # 강한 추세 구간 제외

            long_ok  = (rsi < self.p.rsi_oversold
                        and price <= bb_lower
                        and weak_trend)

            short_ok = (rsi > self.p.rsi_overbought
                        and price >= bb_upper
                        and weak_trend)

            if long_ok:
                size = (self.broker.get_cash() * self.p.position_pct) / price
                if size > 0:
                    self.buy(size=size)
                    self.entry_atr    = atr
                    self._pending_dir = 'long'
            elif short_ok:
                size = (self.broker.get_cash() * self.p.position_pct) / price
                if size > 0:
                    self.sell(size=size)
                    self.entry_atr    = atr
                    self._pending_dir = 'short'

        # ── 청산 ──────────────────────────────────────────
        elif self.position:
            self.bars_held += 1
            is_long = self.position.size > 0

            if is_long:
                stop_hit   = self.data.low[0]  <= self.stop_price
                target_hit = self.data.high[0] >= self.target_price
            else:
                stop_hit   = self.data.high[0] >= self.stop_price
                target_hit = self.data.low[0]  <= self.target_price

            if stop_hit or target_hit or self.bars_held >= self.p.time_exit_bars:
                self.close()
                self._reset()


# ── 백테스트 실행 ──────────────────────────────────────────────
def run_hft(params=None, data_path='backtestDatas/btcusdt_5m.csv',
            initial_cash=100_000.0, plot=False):
    cerebro = bt.Cerebro()

    p = dict(
        rsi_period=3, rsi_oversold=10, rsi_overbought=90,
        bb_period=20, bb_std=2.0,
        adx_period=14, adx_max=30,
        atr_period=7, stop_mult=2.0, target_mult=1.0,
        time_exit_bars=12,
        position_pct=0.99,
    )
    if params:
        p.update(params)

    cerebro.addstrategy(HFTStrategy, **p)

    data = bt.feeds.GenericCSVData(
        dataname   = data_path,
        dtformat   = '%Y-%m-%d %H:%M:%S',
        timeframe  = bt.TimeFrame.Minutes,
        compression= 5,
        openinterest=-1,
        headers    = True,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.0, annualize=True, timeframe=bt.TimeFrame.Minutes)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    result = cerebro.run()
    strat  = result[0]

    ta    = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0
    if total == 0:
        print("거래 없음")
        return None

    won    = ta.won.total
    lost   = ta.lost.total
    avg_p  = ta.won.pnl.average  if won  > 0 else 0.0
    avg_l  = ta.lost.pnl.average if lost > 0 else 0.0
    final  = cerebro.broker.getvalue()
    ror    = (final - initial_cash) / initial_cash * 100
    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio') or 0.0
    mdd    = strat.analyzers.drawdown.get_analysis().get('max', {'drawdown': 0})['drawdown']
    pl     = abs(avg_p / avg_l) if avg_l != 0 else 0.0

    return dict(
        trades=total, won=won, lost=lost,
        win_rate=won/total*100,
        pl_ratio=pl, ror=ror, sharpe=sharpe, mdd=mdd,
        avg_win=avg_p, avg_loss=avg_l,
    )


if __name__ == '__main__':
    import pandas as pd

    df_meta = pd.read_csv('backtestDatas/btcusdt_5m.csv', index_col='Date', parse_dates=True)
    print(f"데이터: {df_meta.index[0].date()} ~ {df_meta.index[-1].date()}  ({len(df_meta):,}봉)")
    print(f"기간: {(df_meta.index[-1]-df_meta.index[0]).days}일\n")

    print("백테스트 실행 중...")
    r = run_hft()

    if r:
        print(f"\n{'='*55}")
        print(f"  BTC 5분봉 HFT 백테스트 결과")
        print(f"  RSI(3) 극단값 평균회귀 | BB(20,2.0) | ADX<30 | ATR×2.0/1.0")
        print(f"{'='*55}")
        print(f"  ROR        : {r['ror']:>+10.2f}%")
        print(f"  Sharpe     : {r['sharpe']:>10.2f}")
        print(f"  MDD        : {r['mdd']:>10.2f}%")
        print(f"{'='*55}")
        print(f"  총 거래    : {r['trades']}회  (수익: {r['won']}, 손실: {r['lost']})")
        print(f"  승률       : {r['win_rate']:.1f}%")
        print(f"  P/L 비     : {r['pl_ratio']:.2f}")
        print(f"  평균 수익  : ${r['avg_win']:>10,.2f}")
        print(f"  평균 손실  : ${r['avg_loss']:>10,.2f}")
        print(f"{'='*55}")
        tpd = r['trades'] / ((df_meta.index[-1] - df_meta.index[0]).days)
        print(f"  일평균 거래: {tpd:.1f}회/일")
        print(f"{'='*55}")
