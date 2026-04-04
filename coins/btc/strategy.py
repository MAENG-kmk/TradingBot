import time
import asyncio
import sys
import os
sys.path.append(os.path.abspath("."))

from coins.base_strategy import BaseCoinStrategy
from tools.sdeTools import barrier_prob, estimate_gbm, sde_entry_probs


class BTCStrategy(BaseCoinStrategy):
    """
    BTC SDE 전략 (실험적)

    기존 볼린저밴드/MACD/RSI 대신, 가격 프로세스를 GBM으로 모델링하고
    이중 장벽 도달 확률(Double Barrier Crossing Probability)로
    진입과 청산을 모두 결정한다.

    진입:
      최근 est_window봉의 log 수익률로 μ, σ 추정 →
      P(+target_ror% 도달 > -stop_ror% 도달) > SDE_ENTRY_PROB 시 진입
      롱/숏 중 더 높은 확률 방향 선택

    청산:
      매 run() 호출마다 현재가 기준 확률 재계산 →
      P(remaining profit) < SDE_EXIT_PROB 이하 시 청산
      하드스탑 / 목표가 도달 / 시간초과 병행
    """

    SYMBOL = "BTCUSDT"
    LEVERAGE = 5
    QUANTITY_PRECISION = 3  # BTC: 0.001 단위

    # ── GBM 파라미터 추정 ──────────────────────────────
    SDE_EST_WINDOW = 50       # 추정 윈도우 (봉)

    # ── 진입 파라미터 ──────────────────────────────────
    SDE_TARGET_ROR  = 0.04    # 목표 수익률 (4%)
    SDE_STOP_ROR    = 0.02    # 손절 비율   (2%)
    SDE_ENTRY_PROB  = 0.58    # 진입 최소 확률

    # ── 청산 파라미터 ──────────────────────────────────
    SDE_EXIT_PROB   = 0.35    # 확률 역전 청산 임계값
    SDE_MAX_BARS    = 48      # 최대 보유 봉 수 (48봉 = 8일)

    # 평균회귀 비활성화 (SDE가 전담)
    MR_ENABLED = False

    # ================================================================
    #  진입 시그널
    # ================================================================

    def check_entry_signal(self):
        """
        GBM 확률 기반 진입 시그널

        Returns:
            ('long'|'short', target_ror_pct, 'sde', meta) | (None, 0, None, None)
        """
        df = self.get_data(limit=300)
        if df is None or len(df) < self.SDE_EST_WINDOW + 1:
            return None, 0, None, None

        # XGBoost 레짐 필터
        if self._rf is not None:
            prob = self._rf.predict(df)
            if prob < 0.55:
                return None, 0, None, None

        closes = df['Close'].values.astype(float)
        mu, sigma = estimate_gbm(closes, window=self.SDE_EST_WINDOW)
        if mu is None:
            return None, 0, None, None

        S = closes[-1]
        p_long, p_short = sde_entry_probs(
            S, self.SDE_TARGET_ROR, self.SDE_STOP_ROR, mu, sigma
        )

        target_pct = self.SDE_TARGET_ROR * 100
        meta = {'mu': mu, 'sigma': sigma, 'p_long': p_long, 'p_short': p_short}

        if p_long > self.SDE_ENTRY_PROB and p_long >= p_short:
            return 'long', target_pct, 'sde', meta

        if p_short > self.SDE_ENTRY_PROB and p_short > p_long:
            return 'short', target_pct, 'sde', meta

        return None, 0, None, None

    # ================================================================
    #  상태 초기화 (진입 직후)
    # ================================================================

    def _init_state(self, target_ror, mode='trend_following', ou=None):
        price = self._get_price()
        if price <= 0:
            price = 1.0  # fallback (실제로 도달하지 않음)

        self._state = {
            'mode': 'sde',
            'entry_time': time.time(),
            'entry_price': price,
            'sde_target': price * (1.0 + self.SDE_TARGET_ROR),
            'sde_stop':   price * (1.0 - self.SDE_STOP_ROR),
            # 기본 필드 (BaseCoinStrategy 일부 메서드 호환용)
            'target_ror':     target_ror,
            'stop_loss':      -(self.SDE_STOP_ROR * 100),
            'highest_ror':    0,
            'trailing_active': False,
            'phase': 1,
        }

    # ================================================================
    #  청산 로직
    # ================================================================

    def _manage_exit(self, position):
        """
        GBM 확률 재계산 → 청산 여부 결정

        청산 조건 (우선순위):
          1. 하드스탑 (현재가 ≤ sde_stop)
          2. 목표 도달 (현재가 ≥ sde_target)
          3. 확률 역전 (P < SDE_EXIT_PROB)
          4. 시간 초과 (SDE_MAX_BARS봉 × 4시간)
        """
        # 재시작 복구: state가 없으면 현재가 기준으로 초기화
        if self._state is None:
            entry_price = float(position.get('enterPrice', 0))
            if entry_price <= 0:
                return
            self._state = {
                'mode': 'sde',
                'entry_time': time.time(),
                'entry_price': entry_price,
                'sde_target': entry_price * (1.0 + self.SDE_TARGET_ROR),
                'sde_stop':   entry_price * (1.0 - self.SDE_STOP_ROR),
                'target_ror': self.SDE_TARGET_ROR * 100,
                'stop_loss':  -(self.SDE_STOP_ROR * 100),
                'highest_ror': 0,
                'trailing_active': False,
                'phase': 1,
            }

        # GBM 파라미터 재추정
        df = self.get_data(limit=self.SDE_EST_WINDOW + 5)
        if df is None or len(df) < self.SDE_EST_WINDOW + 1:
            return

        closes = df['Close'].values.astype(float)
        mu, sigma = estimate_gbm(closes, window=self.SDE_EST_WINDOW)
        if mu is None:
            return

        S         = closes[-1]
        side      = position['side']
        ror       = position['ror']
        sde_target = self._state['sde_target']
        sde_stop   = self._state['sde_stop']

        # 방향에 따른 확률 및 하드레벨 판단
        if side == 'long':
            p_cont   = barrier_prob(S, sde_target, sde_stop, mu, sigma)
            at_target = S >= sde_target
            at_stop   = S <= sde_stop
        else:
            # 숏: target/stop 방향 반전
            sde_target_short = self._state['entry_price'] * (1.0 - self.SDE_TARGET_ROR)
            sde_stop_short   = self._state['entry_price'] * (1.0 + self.SDE_STOP_ROR)
            p_cont   = 1.0 - barrier_prob(S, sde_stop_short, sde_target_short, mu, sigma)
            at_target = S <= sde_target_short
            at_stop   = S >= sde_stop_short

        # 시간 초과 확인
        elapsed   = time.time() - self._state['entry_time']
        max_secs  = self.SDE_MAX_BARS * 4 * 3600
        timed_out = elapsed > max_secs

        # 청산 판단
        should_close = False
        reason = ""

        if at_stop:
            should_close = True
            reason = f"SDE하드스탑({ror:.1f}%)"
        elif at_target:
            should_close = True
            reason = f"SDE목표달성({ror:.1f}%)"
        elif p_cont < self.SDE_EXIT_PROB:
            should_close = True
            reason = f"SDE확률역전(P:{p_cont:.2f}<{self.SDE_EXIT_PROB})"
        elif timed_out:
            should_close = True
            elapsed_h = elapsed / 3600
            reason = f"SDE시간초과({elapsed_h:.0f}h)"

        if should_close:
            self._close_position(position, reason)
        else:
            bars_equiv = elapsed / (4 * 3600)
            print(f"  유지: {self.SYMBOL} | SDE | "
                  f"P:{p_cont:.2f} | ROR:{ror:.1f}% | "
                  f"μ:{mu:.4f} σ:{sigma:.4f} | "
                  f"경과:{bars_equiv:.1f}봉")
