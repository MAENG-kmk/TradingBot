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
from tools.trendFilter import checkTrendStrength, checkMarketRegime
from tools.createOrder import createOrder
from tools.setLeverage import setLeverage
from tools.getBalance import getBalance
from tools.telegram import send_message
from tools.ouProcess import fit_ou
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
    TR_BB_PERIOD = 20           # 추세추종 볼린저밴드 기간
    TR_BB_STD = 2.0             # 추세추종 볼린저밴드 표준편차 배수
    RSI_PERIOD = 14
    RSI_OVERBUY = 80
    RSI_OVERSELL = 20
    ATR_MULTIPLIER = 2.2
    ADX_THRESHOLD = 20
    VOL_PERIOD = 20             # 볼륨 평균 계산 기간
    VOL_MULT = 1.5              # 현재 볼륨 > 평균 × 배수일 때만 진입

    # ===== 청산 파라미터 (4단계 트레일링) =====
    DEFAULT_TARGET_ROR = 10.0
    DEFAULT_STOP_LOSS = -2.5
    PHASE2_THRESHOLD = 3.0    # 본전 확보 진입
    PHASE3_THRESHOLD = 6.0    # 트레일링 시작
    BREAKEVEN_STOP = 0.5      # 본전 확보 시 손절선
    TRAILING_RATIO = 0.6      # 일반 트레일링 (최고 ROR의 60%)
    TIGHT_TRAILING_RATIO = 0.75  # 타이트 트레일링 (75%)
    TIME_EXIT_SECONDS_1 = 86400   # 24시간
    TIME_EXIT_ROR_1 = 1.0
    TIME_EXIT_SECONDS_2 = 172800  # 48시간
    TIME_EXIT_ROR_2 = 2.0
    VOLATILITY_SPIKE = 3.0

    # ===== 평균회귀 파라미터 (OU 프로세스 기반) =====
    MR_ENABLED = True               # 평균회귀 활성화 여부
    MR_SLOPE_THRESHOLD = 0.05       # 횡보 판단 기울기 임계값 (%)
    MR_STOP_LOSS = -1.5             # 손절 (%)
    # OU 파라미터
    MR_OU_ENTRY_Z = 2.0             # 진입 Z-score 임계값 (|Z| > 2.0 → 진입)
    MR_OU_EXIT_Z = 0.5              # 청산 Z-score 임계값 (|Z| < 0.5 → 평균 수렴 완료)
    MR_MAX_HALFLIFE = 12            # 최대 허용 반감기 (봉 단위, 12봉=48h)
    MR_TIME_HALFLIFE_MULT = 2.5     # 시간청산 = 반감기 × 배수

    # ===== VB (Volatility Breakout) 파라미터 - 횡보장 진입 =====
    VB_K = 0.3                   # 트리거: open ± k × prev_range
    VB_MIN_RANGE_PCT = 0.3       # 최소 이전 봉 범위 (%)
    VB_STOP_LOSS = -2.0          # 손절 (%)
    VB_TIME_EXIT_SEC = 14400     # 시간청산 (4H = 14400초)

    def __init__(self, client):
        self.client = client
        self._state = None  # 포지션 상태 (진입 시 생성, 청산 시 초기화)

        # XGBoost 레짐 필터 로드 (models/ 에 없으면 None → 기존 로직 폴백)
        try:
            from tools.regime_filter import RegimeFilter
            self._rf = RegimeFilter.load(f'models/regime_{self.SYMBOL}.pkl')
        except Exception:
            self._rf = None

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

        signal, target_ror, mode, meta = self.check_entry_signal()
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
            ou = meta.get('ou') if meta else None
            self._init_state(target_ror, mode=mode, ou=ou)
            tag = '📊MR' if mode == 'mean_reversion' else ('📈VB' if mode == 'vb' else '✅TR')
            ou_info = f" | HL:{ou['half_life']:.1f}봉 Z:{ou['zscore']:.2f}" if ou else ""
            msg = f"{tag} {self.SYMBOL} {signal.upper()} 진입 | qty:{qty} | target:{target_ror:.1f}%{ou_info}"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
        else:
            print(f"  ❌ {self.SYMBOL} 주문 실패")

    def check_entry_signal(self):
        """
        진입 시그널 체크 — 시장 상태에 따라 전략 분기

        Returns:
            tuple: ('long'|'short', target_ror, mode, meta) | (None, 0, None, None)
              mode: 'trend_following' | 'mean_reversion'
              meta: 추가 정보 dict (ou 파라미터 등)
        """
        df = self.get_data(limit=300)
        if df is None or len(df) < 50:
            return None, 0, None, None

        closes = df['Close'].values.astype(float)

        if self._rf is not None:
            # XGBoost 레짐 분류
            # prob >= 0.55 → 추세장 → 추세추종
            # prob <  0.55 → 횡보장 → VB
            prob = self._rf.predict(df)
            if prob >= 0.55:
                return self._trend_following_signal(df, closes)
            else:
                return self._vb_signal(df, closes)
        else:
            # 폴백: 기존 checkMarketRegime
            regime, adx, slope = checkMarketRegime(
                df, adx_threshold=self.ADX_THRESHOLD,
                slope_threshold=self.MR_SLOPE_THRESHOLD,
            )
            if regime in ('uptrend', 'downtrend'):
                return self._trend_following_signal(df, closes)
            else:
                return self._vb_signal(df, closes)

    def _trend_following_signal(self, df, closes):
        """추세추종 진입 — 볼린저밴드 돌파 + MACD 확인"""
        if len(closes) < self.TR_BB_PERIOD:
            return None, 0, None, None

        # 볼린저밴드 계산
        bb_closes = closes[-self.TR_BB_PERIOD:]
        bb_mid = float(np.mean(bb_closes))
        bb_std = float(np.std(bb_closes))
        bb_upper = bb_mid + self.TR_BB_STD * bb_std
        bb_lower = bb_mid - self.TR_BB_STD * bb_std

        current_price = closes[-1]
        rsi = self._rsi(closes)
        macd, signal = self._macd(closes)
        if macd is None:
            return None, 0, None, None

        atr = getATR(df)
        target_ror = abs(atr / closes[-1]) * 100

        if rsi >= self.RSI_OVERBUY or rsi <= self.RSI_OVERSELL:
            return None, 0, None, None

        # 볼륨 필터 — 가짜 돌파 방지
        volumes = df['Volume'].values.astype(float)
        avg_vol = float(np.mean(volumes[-self.VOL_PERIOD:]))
        current_vol = volumes[-1]
        if avg_vol <= 0 or current_vol < avg_vol * self.VOL_MULT:
            return None, 0, None, None

        # BB 상단 돌파 + MACD 확인 → 롱
        if current_price > bb_upper and macd > signal:
            return 'long', target_ror, 'trend_following', {}
        # BB 하단 돌파 + MACD 확인 → 숏
        if current_price < bb_lower and macd < signal:
            return 'short', target_ror, 'trend_following', {}

        return None, 0, None, None

    def _mean_reversion_signal(self, df, closes):
        """
        평균회귀 진입 — OU 프로세스 기반

        1. OU 파라미터 추정 (AR(1) OLS)
        2. 반감기 필터: half_life > MR_MAX_HALFLIFE → 회귀 너무 느림 → 스킵
        3. Z-score 진입: |Z| > MR_OU_ENTRY_Z
           Z < -2.0: 로그가격이 장기 평균 아래 → 롱
           Z > +2.0: 로그가격이 장기 평균 위  → 숏
        """
        if len(closes) < 30:
            return None, 0, None, None

        ou = fit_ou(closes)
        if ou is None:
            return None, 0, None, None

        # 반감기 필터 — 회귀가 너무 느리면 진입 안 함
        if ou['half_life'] > self.MR_MAX_HALFLIFE:
            return None, 0, None, None

        z = ou['zscore']

        # 목표 수익: OU sigma_eq 기반 동적 계산 (Z 진입점 → 평균까지의 80%)
        target_ror = abs(z) * float(ou['sigma_eq']) * 100 * 0.8

        if z <= -self.MR_OU_ENTRY_Z:
            return 'long', max(target_ror, 1.5), 'mean_reversion', {'ou': ou}
        if z >= self.MR_OU_ENTRY_Z:
            return 'short', max(target_ror, 1.5), 'mean_reversion', {'ou': ou}

        return None, 0, None, None

    def _vb_signal(self, df, closes):
        """
        변동성 돌파 진입 — 횡보장 전용 (같은 봉 내 진입/청산)

        트리거: open + k × prev_range (롱) / open - k × prev_range (숏)
        현재 봉이 트리거를 터치했으면 시그널 발생
        """
        if len(df) < 2:
            return None, 0, None, None

        prev = df.iloc[-2]
        cur = df.iloc[-1]

        prev_range = float(prev['High'] - prev['Low'])
        prev_close = float(prev['Close'])
        if prev_close <= 0 or prev_range <= 0:
            return None, 0, None, None

        # 이전 봉 범위가 너무 작으면 노이즈 — 스킵
        if prev_range / prev_close * 100 < self.VB_MIN_RANGE_PCT:
            return None, 0, None, None

        cur_open = float(cur['Open'])
        cur_high = float(cur['High'])
        cur_low = float(cur['Low'])

        long_trig = cur_open + self.VB_K * prev_range
        short_trig = cur_open - self.VB_K * prev_range

        long_ok = cur_high >= long_trig and long_trig > cur_open
        short_ok = cur_low <= short_trig and short_trig < cur_open

        # 양방향 동시 돌파 → 노이즈
        if long_ok and short_ok:
            return None, 0, None, None

        if long_ok:
            return 'long', abs(self.VB_STOP_LOSS) * 1.5, 'vb', {}
        if short_ok:
            return 'short', abs(self.VB_STOP_LOSS) * 1.5, 'vb', {}

        return None, 0, None, None

    # ================================================================
    #  청산 로직 (BetController 4단계 트레일링 내장)
    # ================================================================

    def _manage_exit(self, position):
        ror = position['ror']

        # 재시작 복구: state 없으면 기본값으로 초기화
        if self._state is None:
            self._init_state(0)

        mode = self._state.get('mode', 'trend_following')

        # VB 모드: 손절 / 목표 / 4H 시간청산
        if mode == 'vb':
            should_close = False
            reason = ""

            # 1. 손절
            if ror <= self._state['stop_loss']:
                should_close = True
                reason = f"VB손절({ror:.1f}%)"

            # 2. 목표 수익
            if not should_close and ror >= self._state['target_ror']:
                should_close = True
                reason = f"VB목표달성({ror:.1f}%≥{self._state['target_ror']:.1f}%)"

            # 3. 시간 청산 (4H)
            if not should_close:
                if time.time() - self._state['entry_time'] > self.VB_TIME_EXIT_SEC:
                    should_close = True
                    reason = f"VB시간초과(4H, ROR:{ror:.1f}%)"

            if should_close:
                self._close_position(position, reason)
            else:
                print(f"  유지: {self.SYMBOL} | VB | ROR:{ror:.1f}% | 목표:{self._state['target_ror']:.1f}% | 손절:{self._state['stop_loss']:.1f}%")
            return

        # 평균회귀 모드: OU Z-score 수렴 or 목표/손절/시간 청산
        if mode == 'mean_reversion':
            should_close = False
            reason = ""

            # 1. OU Z-score 수렴 청산 (가장 우선)
            ou_mu       = self._state.get('ou_mu')
            ou_sigma_eq = self._state.get('ou_sigma_eq')
            if ou_mu is not None and ou_sigma_eq and ou_sigma_eq > 0:
                try:
                    current_price = self._get_price()
                    if current_price > 0:
                        import math
                        current_z = (math.log(current_price) - ou_mu) / ou_sigma_eq
                        if abs(current_z) < self.MR_OU_EXIT_Z:
                            should_close = True
                            reason = f"MR평균수렴(Z:{current_z:.2f})"
                except Exception:
                    pass

            # 2. 목표 수익 도달
            if not should_close and ror >= self._state['target_ror']:
                should_close = True
                reason = f"MR목표달성({ror:.1f}%≥{self._state['target_ror']:.1f}%)"

            # 3. 손절
            if not should_close and ror <= self._state['stop_loss']:
                should_close = True
                reason = f"MR손절({ror:.1f}%)"

            # 4. 시간 청산 (반감기 기반 동적)
            if not should_close:
                time_limit = self._state.get('mr_time_exit_sec', 43200)
                if time.time() - self._state['entry_time'] > time_limit:
                    should_close = True
                    hl = self._state.get('ou_half_life', 3)
                    reason = f"MR시간초과({hl:.1f}봉×{self.MR_TIME_HALFLIFE_MULT}배)"

            if should_close:
                self._close_position(position, reason)
            else:
                hl = self._state.get('ou_half_life', '?')
                print(f"  유지: {self.SYMBOL} | MR | ROR:{ror:.1f}% | 목표:{self._state['target_ror']:.1f}% | HL:{hl:.1f}봉")
            return

        # 추세추종 모드: 기존 4단계 트레일링
        # 1. 트레일링 스탑 업데이트
        self._update_trailing(ror)

        should_close = False
        reason = ""
        is_hard_stop = False

        # 2. 손절 / 트레일링 스탑
        if ror < self._state['stop_loss']:
            should_close = True
            if self._state['trailing_active']:
                reason = f"트레일링스탑(최고:{self._state['highest_ror']:.1f}%→현재:{ror:.1f}%)"
            else:
                reason = f"손절({ror:.1f}%)"
                is_hard_stop = True

        # 3. 변동성 급변
        if not should_close:
            should_close, reason = self._check_volatility()

        # 4. 시간 기반 청산
        if not should_close:
            should_close, reason = self._check_time()

        if should_close:
            # 재진입 방지: 하드스탑 외 청산 시, 같은 방향 시그널이면 보류
            if not is_hard_stop and self._should_hold(position['side']):
                print(f"  보류: {self.SYMBOL} | {reason} 조건이나 동일방향 시그널 존재 → 홀드")
            else:
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

    def _init_state(self, target_ror, mode='trend_following', ou=None):
        if mode == 'vb':
            self._state = {
                'target_ror': target_ror,
                'stop_loss': self.VB_STOP_LOSS,
                'entry_time': time.time(),
                'highest_ror': 0,
                'atr_ratio': 0.03,
                'trailing_active': False,
                'phase': 1,
                'mode': 'vb',
            }
            return

        if mode == 'mean_reversion':
            half_life = ou['half_life'] if ou else 6.0
            # 시간청산: 반감기 × 배수 (초 단위, 1봉=4h=14400초)
            time_exit_sec = half_life * self.MR_TIME_HALFLIFE_MULT * 14400
            self._state = {
                'target_ror': target_ror,
                'stop_loss': self.MR_STOP_LOSS,
                'entry_time': time.time(),
                'highest_ror': 0,
                'atr_ratio': 0.03,
                'trailing_active': False,
                'phase': 1,
                'mode': 'mean_reversion',
                # OU 파라미터 (청산 판단용)
                'ou_mu'      : ou['mu']       if ou else None,
                'ou_sigma_eq': ou['sigma_eq'] if ou else None,
                'ou_half_life': half_life,
                'mr_time_exit_sec': time_exit_sec,
            }
            return

        if target_ror <= 5:
            target = self.DEFAULT_TARGET_ROR
            stop = self.DEFAULT_STOP_LOSS
            atr_ratio = 0.05
        else:
            target = target_ror
            stop = -0.33 * target_ror  # 3:1 손익비
            atr_ratio = target_ror / 100

        self._state = {
            'target_ror': target,
            'stop_loss': stop,
            'entry_time': time.time(),
            'highest_ror': 0,
            'atr_ratio': atr_ratio,
            'trailing_active': False,
            'phase': 1,
            'mode': 'trend_following',
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

    def _should_hold(self, current_side):
        """
        재진입 방지 — 청산 직전 진입 시그널 확인

        현재 포지션과 같은 방향의 진입 시그널이 있으면 True (홀드)
        → 청산 후 즉시 재진입하는 낭비를 방지
        """
        try:
            signal, _, _, _ = self.check_entry_signal()
            if signal is not None and signal == current_side:
                return True
        except Exception:
            pass
        return False

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

