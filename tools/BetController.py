import sys
import os
import time
sys.path.append(os.path.abspath("."))
from tools.getData import get4HData
from tools.getAtr import getATR


class BetController:
  """
  포지션 청산 관리 (고도화)
  
  청산 조건 (우선순위):
    1. 긴급 손절: ATR 기반 동적 손절선 이탈
    2. 시간 기반 청산: 일정 시간 경과 후 수익 없으면 정리
    3. 트레일링 스탑: 수익 구간별 차등 트레일링
    4. 동적 익절: ATR 기반 변동성 연동 목표 수익률
    5. 부분 청산: 1차 익절 도달 시 절반 청산 (미구현 - 바이낸스 API 제약)
  """
  
  def __init__(self, client, logicList):
    self.client = client
    self.logicList = logicList
    
    # 포지션별 상태 저장
    # {symbol: {target_ror, stop_loss, entry_time, highest_ror, atr_ratio, trailing_active}}
    self.positions = {}
    
    # 기본 설정
    self.defaultTargetRor = 7
    self.defaultStopLoss = -4
    
    # 호환용 (기존 코드에서 접근하는 경우)
    self.targetRorChecker = {}
  
  def saveNew(self, symbol, targetRor):
    """
    새 포지션 등록 (기존 인터페이스 유지)
    
    ATR 기반 동적 손절/익절 설정:
    - targetRor이 높으면(변동성 큼) → 넓은 손절, 높은 익절
    - targetRor이 낮으면(변동성 작음) → 좁은 손절, 낮은 익절
    """
    if targetRor <= 5:
      target = self.defaultTargetRor
      stop = self.defaultStopLoss
      atr_ratio = 0.05  # 기본 변동성
    else:
      target = targetRor
      stop = -0.4 * targetRor  # 손익비 2.5:1 유지
      atr_ratio = targetRor / 100
    
    self.positions[symbol] = {
      'target_ror': target,
      'stop_loss': stop,
      'entry_time': time.time(),
      'highest_ror': 0,
      'atr_ratio': atr_ratio,
      'trailing_active': False,
      'phase': 1,  # 1: 초기, 2: 수익 진입, 3: 트레일링
    }
    
    # 기존 호환
    self.targetRorChecker[symbol] = [target, stop]
  
  def _update_trailing_stop(self, symbol, ror):
    """
    수익 구간별 차등 트레일링 스탑 업데이트
    
    구간별 전략:
    - 0~3%: 고정 손절 유지 (초기)
    - 3~5%: 본전 이상으로 손절 상향 (본전 확보)
    - 5~목표: 트레일링 시작 (최고점 대비 40% 되돌림에서 청산)
    - 목표 초과: 타이트 트레일링 (최고점 대비 25% 되돌림)
    """
    pos = self.positions[symbol]
    
    # 최고 수익률 갱신
    if ror > pos['highest_ror']:
      pos['highest_ror'] = ror
    
    highest = pos['highest_ror']
    
    # 구간 1: 0~3% → 고정 손절 유지
    if highest < 3:
      pos['phase'] = 1
      return
    
    # 구간 2: 3~5% → 본전 확보 (손절을 0% 이상으로)
    if highest < 5:
      pos['phase'] = 2
      new_stop = max(pos['stop_loss'], 0.5)  # 최소 +0.5%에서 청산
      pos['stop_loss'] = new_stop
      return
    
    # 구간 3: 5~목표 → 트레일링 (40% 되돌림)
    if highest < pos['target_ror']:
      pos['phase'] = 3
      pos['trailing_active'] = True
      trailing_stop = highest * 0.6  # 최고점의 60% 지점
      pos['stop_loss'] = max(pos['stop_loss'], trailing_stop)
      return
    
    # 구간 4: 목표 초과 → 타이트 트레일링 (25% 되돌림)
    pos['phase'] = 3
    pos['trailing_active'] = True
    trailing_stop = highest * 0.75  # 최고점의 75% 지점
    pos['stop_loss'] = max(pos['stop_loss'], trailing_stop)
  
  def _check_time_exit(self, symbol):
    """
    시간 기반 청산 체크
    
    - 24시간(86400초) 경과 후 수익이 1% 미만이면 청산 권고
    - 48시간 경과 후 수익이 2% 미만이면 청산 권고
    → 자금이 묶이는 것을 방지
    """
    pos = self.positions[symbol]
    elapsed = time.time() - pos['entry_time']
    ror = pos['highest_ror']
    
    # 24시간 경과 & 수익 1% 미만
    if elapsed > 86400 and ror < 1:
      return True, "시간초과(24h, ROR<1%)"
    
    # 48시간 경과 & 수익 2% 미만
    if elapsed > 172800 and ror < 2:
      return True, "시간초과(48h, ROR<2%)"
    
    return False, ""
  
  def _check_volatility_exit(self, symbol):
    """
    변동성 급변 시 긴급 청산 체크
    현재 ATR이 진입 시점 대비 3배 이상이면 → 시장 급변, 청산
    """
    try:
      data = get4HData(self.client, symbol, 20)
      if len(data) < 10:
        return False, ""
      
      current_atr = getATR(data)
      current_price = float(data.iloc[-1]['Close'])
      current_atr_ratio = current_atr / current_price
      
      entry_atr_ratio = self.positions[symbol]['atr_ratio']
      
      if entry_atr_ratio > 0 and current_atr_ratio > entry_atr_ratio * 3:
        return True, f"변동성급변(ATR {entry_atr_ratio:.4f}→{current_atr_ratio:.4f})"
      
      return False, ""
    except Exception as e:
      return False, ""
  
  def decideGoOrStop(self, data, currentPosition):
    """로직 기반 유지/청산 결정 (기존 인터페이스 유지)"""
    for logic in self.logicList:
      side = logic(data)
      if side == currentPosition:
        continue
      else:
        return 'Stop'
    return 'Go'
  
  def getClosePositions(self, positions):
    """
    청산 대상 포지션 결정 (기존 인터페이스 유지)
    
    판단 순서:
    1. 긴급 손절 (고정 손절선 이탈)
    2. 변동성 급변 청산
    3. 시간 기반 청산
    4. 트레일링 스탑 (동적 손절선)
    5. 동적 익절 도달 (트레일링으로 전환하므로 바로 청산하지 않음)
    """
    list_to_close = []
    
    for position in positions:
      symbol = position['symbol']
      ror = position['ror']
      
      # 미등록 포지션 → 기본값으로 등록
      if symbol not in self.positions:
        self.saveNew(symbol, 0)
      
      pos = self.positions[symbol]
      
      # === 1. 트레일링 스탑 업데이트 ===
      self._update_trailing_stop(symbol, ror)
      
      should_close = False
      reason = ""
      
      # === 2. 손절 체크 (트레일링 포함) ===
      if ror < pos['stop_loss']:
        should_close = True
        if pos['trailing_active']:
          reason = f"트레일링스탑(phase:{pos['phase']}, 최고:{pos['highest_ror']:.1f}%, 청산:{ror:.1f}%)"
        else:
          reason = f"손절({ror:.1f}% < {pos['stop_loss']:.1f}%)"
      
      # === 3. 변동성 급변 체크 ===
      if not should_close:
        vol_exit, vol_reason = self._check_volatility_exit(symbol)
        if vol_exit:
          should_close = True
          reason = vol_reason
      
      # === 4. 시간 기반 청산 ===
      if not should_close:
        time_exit, time_reason = self._check_time_exit(symbol)
        if time_exit:
          should_close = True
          reason = time_reason
      
      # === 청산 실행 ===
      if should_close:
        print(f"  청산: {symbol} | {reason}")
        list_to_close.append(position)
        self.positions.pop(symbol, None)
        self.targetRorChecker.pop(symbol, None)
      else:
        # 상태 로그
        phase_names = {1: "초기", 2: "본전확보", 3: "트레일링"}
        phase_name = phase_names.get(pos['phase'], "?")
        print(f"  유지: {symbol} | ROR:{ror:.1f}% | 목표:{pos['target_ror']:.1f}% | 손절:{pos['stop_loss']:.1f}% | {phase_name}")
    
    return list_to_close