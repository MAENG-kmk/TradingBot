"""
BTC SDE (Geometric Brownian Motion) 기반 백테스트 전략

기존 기술적 지표(BB, MACD, RSI) 대신, 가격 프로세스 자체를 GBM으로 모델링하고
이중 장벽 도달 확률(Double Barrier Crossing Probability)로 진입·청산을 결정한다.

진입:
  GBM 파라미터(μ, σ) 추정 → P(목표가 도달 > 손절가 도달) > entry_prob 시 진입
  롱/숏 중 더 높은 확률의 방향으로 진입

청산:
  매 봉마다 현재가 기준으로 확률 재계산
  P(remaining profit) < exit_prob → 기대값 역전 → 청산
  하드스탑(entry × stop_ror), 시간청산(max_bars) 병행

사용법:
  python backtestStrategy/SDEStrategy.py
  python backtestStrategy/SDEStrategy.py --target_ror 0.05 --stop_ror 0.025 --entry_prob 0.62
"""

import sys
import os
sys.path.append(os.path.abspath("."))

import backtrader as bt
import numpy as np

from tools.sdeTools import barrier_prob, estimate_gbm, sde_entry_probs


class SDEStrategy(bt.Strategy):
    """
    GBM 이중 장벽 확률 기반 진입·청산 전략

    Params:
        est_window  : GBM 파라미터 추정 윈도우 (봉)
        target_ror  : 목표 수익률 (e.g. 0.04 = 4%)
        stop_ror    : 손절 비율   (e.g. 0.02 = 2%)
        entry_prob  : 진입 최소 확률 (e.g. 0.60 = 60%)
        exit_prob   : 청산 트리거 확률 (e.g. 0.40 = 40%)
        max_bars    : 최대 보유 봉 수
        risk_percent: 봉당 리스크 비율 (자본 대비)
    """

    params = dict(
        est_window=50,
        target_ror=0.04,
        stop_ror=0.02,
        entry_prob=0.60,
        exit_prob=0.40,
        max_bars=48,
        risk_percent=0.02,
        leverage=1,          # 레버리지 (P&L 배수, 포지션 크기는 동일)
    )

    def __init__(self):
        self._pending_entry = None
        self._reset()

    def _reset(self):
        self.entry_price = 0.0
        self.direction   = None
        self.sde_target  = 0.0
        self.sde_stop    = 0.0
        self.bars_held   = 0

    def _get_prices(self):
        n = self.p.est_window + 1
        if len(self.data) < n:
            return None
        return np.array(
            [self.data.close[-(n - 1 - i)] for i in range(n)], dtype=float
        )

    def notify_order(self, order):
        """실제 체결가(다음 봉 시가)로 진입가·목표·손절 기록"""
        if order.status == order.Completed and self._pending_entry is not None:
            direction = self._pending_entry['direction']
            self._pending_entry = None

            fill = order.executed.price
            self._reset()
            self.entry_price = fill
            self.direction   = direction

            if direction == 'long':
                self.sde_target = fill * (1.0 + self.p.target_ror)
                self.sde_stop   = fill * (1.0 - self.p.stop_ror)
            else:
                self.sde_target = fill * (1.0 - self.p.target_ror)
                self.sde_stop   = fill * (1.0 + self.p.stop_ror)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._pending_entry = None

    def next(self):
        prices = self._get_prices()
        if prices is None:
            return

        mu, sigma = estimate_gbm(prices, window=self.p.est_window)
        if mu is None:
            return

        S = float(self.data.close[0])

        # ── 진입 ──────────────────────────────────────────
        if not self.position:
            p_long, p_short = sde_entry_probs(
                S, self.p.target_ror, self.p.stop_ror, mu, sigma
            )

            if p_long > self.p.entry_prob and p_long >= p_short:
                size = (self.broker.get_cash() * self.p.risk_percent) \
                       / (S * self.p.stop_ror)
                if size > 0:
                    self.buy(size=size)
                    self._pending_entry = {'direction': 'long'}

            elif p_short > self.p.entry_prob and p_short > p_long:
                size = (self.broker.get_cash() * self.p.risk_percent) \
                       / (S * self.p.stop_ror)
                if size > 0:
                    self.sell(size=size)
                    self._pending_entry = {'direction': 'short'}

        # ── 청산 ──────────────────────────────────────────
        else:
            self.bars_held += 1

            if self.direction == 'long':
                # 현재가에서 원래 목표/손절까지 확률 재계산
                p_cont   = barrier_prob(S, self.sde_target, self.sde_stop, mu, sigma)
                at_target = S >= self.sde_target
                at_stop   = S <= self.sde_stop
            else:
                # 숏: P(hit lower target before upper stop)
                p_cont   = 1.0 - barrier_prob(
                    S, self.sde_stop, self.sde_target, mu, sigma
                )
                at_target = S <= self.sde_target
                at_stop   = S >= self.sde_stop

            should_close = (
                at_stop                             # 하드스탑
                or at_target                        # 목표 달성
                or p_cont < self.p.exit_prob        # 확률 역전
                or self.bars_held >= self.p.max_bars  # 시간 청산
            )

            if should_close:
                self.close()
                self._reset()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='SDE 전략 백테스트')
    parser.add_argument('--data',       default='backtestDatas/btcusdt_4h.csv')
    parser.add_argument('--cash',       type=float, default=100_000.0)
    parser.add_argument('--est_window', type=int,   default=50)
    parser.add_argument('--target_ror', type=float, default=0.04)
    parser.add_argument('--stop_ror',   type=float, default=0.02)
    parser.add_argument('--entry_prob', type=float, default=0.60)
    parser.add_argument('--exit_prob',  type=float, default=0.40)
    parser.add_argument('--max_bars',   type=int,   default=48)
    args = parser.parse_args()

    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        SDEStrategy,
        est_window=args.est_window,
        target_ror=args.target_ror,
        stop_ror=args.stop_ror,
        entry_prob=args.entry_prob,
        exit_prob=args.exit_prob,
        max_bars=args.max_bars,
    )

    data = bt.feeds.GenericCSVData(
        dataname=args.data,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(args.cash)
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    print(f"\n{'='*60}")
    print(f"SDE 전략 백테스트: {os.path.basename(args.data)}")
    print(f"est_window={args.est_window} | "
          f"target={args.target_ror:.1%} | stop={args.stop_ror:.1%}")
    print(f"entry_prob={args.entry_prob:.0%} | "
          f"exit_prob={args.exit_prob:.0%} | max_bars={args.max_bars}")
    print(f"{'='*60}")

    result = cerebro.run()
    strat  = result[0]

    ta    = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0

    if total == 0:
        print("거래 없음 — 파라미터를 조정해보세요.")
    else:
        won   = ta.won.total
        lost  = ta.lost.total
        avg_p = ta.won.pnl.average  if won  > 0 else 0.0
        avg_l = ta.lost.pnl.average if lost > 0 else 0.0
        final = cerebro.broker.getvalue()
        ror   = (final - args.cash) / args.cash * 100
        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0) or 0
        mdd    = strat.analyzers.drawdown.get_analysis() \
                     .get('max', {'drawdown': 0})['drawdown']
        pl     = abs(avg_p / avg_l) if avg_l != 0 else 0.0

        print(f"총 거래  : {total}회  (수익: {won}, 손실: {lost})")
        print(f"승률     : {won / total * 100:.1f}%")
        print(f"P/L 비   : {pl:.2f}")
        print(f"ROR      : {ror:.2f}%")
        print(f"Sharpe   : {sharpe:.2f}")
        print(f"MDD      : {mdd:.2f}%")
        print(f"최종 잔고: ${final:,.2f}")
