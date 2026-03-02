import math
import time
import asyncio
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.abspath("."))
from datetime import datetime

from tools.getData import get4HData
from tools.getAtr import getATR
from tools.trendFilter import checkTrendStrength
from tools.createOrder import createOrder
from tools.setLeverage import setLeverage
from tools.getBalance import getBalance
from tools.telegram import send_message
from MongoDB_python.client import addDataToMongoDB


class BaseCoinStrategy:
    """
    코인별 전략 베이스 클래스 — 진입/청산 모두 자체 관리

    main.py에서는 strategy.run()만 호출하면 됨.

    서브클래스에서 오버라이드:
      - SYMBOL, LEVERAGE, QUANTITY_PRECISION
      - 진입 파라미터 (EMA, RSI, MACD, ADX 등)
      - 청산 파라미터 (트레일링 비율, 시간 청산 등)
      - check_entry_signal(): 코인별 커스텀 진입 로직
    """

    # ===== 기본 설정 =====
    SYMBOL = ""
    LEVERAGE = 1
    QUANTITY_PRECISION = 3

    # ===== 진입 파라미터 =====
    EMA_SHORT = 10
    EMA_LONG = 30
    RSI_PERIOD = 14
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ATR_MULTIPLIER = 2.2
    ADX_THRESHOLD = 20

    # ===== 청산 파라미터 (4단계 트레일링) =====
    DEFAULT_TARGET_ROR = 7.0
    DEFAULT_STOP_LOSS = -4.0
    PHASE2_THRESHOLD = 3.0    # 본전 확보 진입
    PHASE3_THRESHOLD = 5.0    # 트레일링 시작
    BREAKEVEN_STOP = 0.5      # 본전 확보 시 손절선
    TRAILING_RATIO = 0.6      # 일반 트레일링 (최고 ROR의 60%)
    TIGHT_TRAILING_RATIO = 0.75  # 타이트 트레일링 (75%)
    TIME_EXIT_SECONDS_1 = 86400   # 24시간
    TIME_EXIT_ROR_1 = 1.0
    TIME_EXIT_SECONDS_2 = 172800  # 48시간
    TIME_EXIT_ROR_2 = 2.0
    VOLATILITY_SPIKE = 3.0

    def __init__(self, client):
        self.client = client
        self._state = None  # 포지션 상태 (진입 시 생성, 청산 시 초기화)

    # ================================================================
    #  main.py에서 호출하는 유일한 메서드
    # ================================================================

    def run(self, positions, total_balance, available_balance):
        """
        진입/청산 전체 관리

        Args:
            positions: getPositions() 결과
            total_balance: 총 잔고
            available_balance: 가용 잔고
        """
        position = next((p for p in positions if p['symbol'] == self.SYMBOL), None)

        if position:
            self._manage_exit(position)
        else:
            self._state = None
            self._manage_entry(total_balance, available_balance)

    # ================================================================
    #  진입 로직
    # ================================================================

    def _manage_entry(self, total_balance, available_balance):
        bullet = float(total_balance) / 10 * 0.99
        if float(available_balance) < bullet:
            return

        signal, target_ror = self.check_entry_signal()
        if signal is None:
            return

        price = self._get_price()
        if price <= 0:
            return
        qty = self._calc_quantity(bullet, price)
        if qty <= 0:
            return

        side = 'BUY' if signal == 'long' else 'SELL'
        setLeverage(self.client, self.SYMBOL, self.LEVERAGE)
        response = createOrder(self.client, self.SYMBOL, side, 'MARKET', qty)

        if response:
            self._init_state(target_ror)
            msg = f"✅ {self.SYMBOL} {signal.upper()} 진입 | qty:{qty} | target:{target_ror:.1f}%"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
        else:
            print(f"  ❌ {self.SYMBOL} 주문 실패")

    def check_entry_signal(self):
        """
        진입 시그널 체크 — 서브클래스에서 오버라이드 가능

        Returns:
            tuple: ('long', target_ror) | ('short', target_ror) | (None, 0)
        """
        df = self.get_data()
        if df is None or len(df) < 50:
            return None, 0

        closes = df['Close'].values.astype(float)

        if not checkTrendStrength(df, adx_threshold=self.ADX_THRESHOLD):
            return None, 0

        ema_short = self._ema(closes, self.EMA_SHORT)
        ema_long = self._ema(closes, self.EMA_LONG)
        rsi = self._rsi(closes)
        macd, signal = self._macd(closes)
        if macd is None:
            return None, 0

        atr = getATR(df)
        target_ror = abs(atr / closes[-1]) * 100

        if rsi >= self.RSI_OVERBUY or rsi <= self.RSI_OVERSELL:
            return None, 0

        if ema_short > ema_long and macd > signal:
            return 'long', target_ror
        if ema_short < ema_long and macd < signal:
            return 'short', target_ror

        return None, 0

    # ================================================================
    #  청산 로직 (BetController 4단계 트레일링 내장)
    # ================================================================

    def _manage_exit(self, position):
        ror = position['ror']

        # 재시작 복구: state 없으면 기본값으로 초기화
        if self._state is None:
            self._init_state(0)

        # 1. 트레일링 스탑 업데이트
        self._update_trailing(ror)

        should_close = False
        reason = ""

        # 2. 손절 / 트레일링 스탑
        if ror < self._state['stop_loss']:
            should_close = True
            if self._state['trailing_active']:
                reason = f"트레일링스탑(최고:{self._state['highest_ror']:.1f}%→현재:{ror:.1f}%)"
            else:
                reason = f"손절({ror:.1f}%)"

        # 3. 변동성 급변
        if not should_close:
            should_close, reason = self._check_volatility()

        # 4. 시간 기반 청산
        if not should_close:
            should_close, reason = self._check_time()

        if should_close:
            self._close_position(position, reason)
        else:
            phase_names = {1: "초기", 2: "본전확보", 3: "트레일링", 4: "타이트"}
            phase = phase_names.get(self._state['phase'], "?")
            print(f"  유지: {self.SYMBOL} | ROR:{ror:.1f}% | 손절:{self._state['stop_loss']:.1f}% | {phase}")

    def _close_position(self, position, reason):
        close_side = 'SELL' if position['side'] == 'long' else 'BUY'
        response = createOrder(self.client, self.SYMBOL, close_side, 'MARKET', position['amount'])

        if response:
            # MongoDB 기록
            try:
                balance, _ = getBalance(self.client)
                data = dict(position)
                data['closeTime'] = int(datetime.now().timestamp())
                data['balance'] = balance
                addDataToMongoDB([data])
            except Exception:
                pass

            msg = f"🔴 {self.SYMBOL} 청산 ({reason}) | ROR:{position['ror']:.1f}% | 손익:{position['profit']:.2f}$"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

            self._state = None
        else:
            print(f"  ❌ {self.SYMBOL} 청산 주문 실패")

    # ===== 4단계 트레일링 스탑 =====

    def _init_state(self, target_ror):
        if target_ror <= 5:
            target = self.DEFAULT_TARGET_ROR
            stop = self.DEFAULT_STOP_LOSS
            atr_ratio = 0.05
        else:
            target = target_ror
            stop = -0.4 * target_ror  # 손익비 2.5:1
            atr_ratio = target_ror / 100

        self._state = {
            'target_ror': target,
            'stop_loss': stop,
            'entry_time': time.time(),
            'highest_ror': 0,
            'atr_ratio': atr_ratio,
            'trailing_active': False,
            'phase': 1,
        }

    def _update_trailing(self, ror):
        s = self._state
        if ror > s['highest_ror']:
            s['highest_ror'] = ror
        highest = s['highest_ror']

        # Phase 1: 0~3% → 고정 손절 유지
        if highest < self.PHASE2_THRESHOLD:
            s['phase'] = 1
            return
        # Phase 2: 3~5% → 본전 확보
        if highest < self.PHASE3_THRESHOLD:
            s['phase'] = 2
            s['stop_loss'] = max(s['stop_loss'], self.BREAKEVEN_STOP)
            return
        # Phase 3: 5~목표 → 트레일링
        if highest < s['target_ror']:
            s['phase'] = 3
            s['trailing_active'] = True
            s['stop_loss'] = max(s['stop_loss'], highest * self.TRAILING_RATIO)
            return
        # Phase 4: 목표 초과 → 타이트 트레일링
        s['phase'] = 4
        s['trailing_active'] = True
        s['stop_loss'] = max(s['stop_loss'], highest * self.TIGHT_TRAILING_RATIO)

    def _check_time(self):
        elapsed = time.time() - self._state['entry_time']
        ror = self._state['highest_ror']
        if elapsed > self.TIME_EXIT_SECONDS_1 and ror < self.TIME_EXIT_ROR_1:
            return True, f"시간초과(24h, ROR<{self.TIME_EXIT_ROR_1}%)"
        if elapsed > self.TIME_EXIT_SECONDS_2 and ror < self.TIME_EXIT_ROR_2:
            return True, f"시간초과(48h, ROR<{self.TIME_EXIT_ROR_2}%)"
        return False, ""

    def _check_volatility(self):
        try:
            data = get4HData(self.client, self.SYMBOL, 20)
            if data is None or len(data) < 10:
                return False, ""
            current_atr = getATR(data)
            current_price = float(data.iloc[-1]['Close'])
            current_ratio = current_atr / current_price
            entry_ratio = self._state['atr_ratio']
            if entry_ratio > 0 and current_ratio > entry_ratio * self.VOLATILITY_SPIKE:
                return True, f"변동성급변(ATR {entry_ratio:.4f}→{current_ratio:.4f})"
        except Exception:
            pass
        return False, ""

    # ================================================================
    #  유틸리티
    # ================================================================

    def get_data(self, limit=100):
        return get4HData(self.client, self.SYMBOL, limit)

    def _get_price(self):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=self.SYMBOL)
            return float(ticker['price'])
        except Exception:
            return 0

    def _calc_quantity(self, bullet, price):
        precision = 10 ** self.QUANTITY_PRECISION
        return math.floor((bullet / price) * precision) / precision

    def _ema(self, closes, period):
        if len(closes) < period:
            return float(closes[-1])
        return float(pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1])

    def _rsi(self, closes):
        if len(closes) < self.RSI_PERIOD + 1:
            return 50
        s = pd.Series(closes)
        delta = s.diff()
        gain = delta.where(delta > 0, 0).rolling(self.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.RSI_PERIOD).mean()
        rs = gain / loss
        return float((100 - (100 / (1 + rs))).iloc[-1])

    def _macd(self, closes):
        if len(closes) < 26:
            return None, None
        s = pd.Series(closes)
        ema12 = s.ewm(span=12, adjust=False).mean()
        ema26 = s.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return float(macd.iloc[-1]), float(signal.iloc[-1])

