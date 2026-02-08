# ETH 자동매매 전략 (OptimizedStrategy)

## 개요

이 자동매매 봇은 **백테스트로 검증된 OptimizedStrategy**를 실제 거래에 적용합니다.

### 성능 지표 (백테스트 기준: ETH 4시간 봉, 2021-2024)
- **수익률(ROR)**: +91.71%
- **Sharpe Ratio**: 0.64
- **최대낙폭(MDD)**: 25.85%
- **거래 횟수**: 440회
- **승률**: 42.0%
- **수익/손실 비율**: 1.68
- **평균 수익**: $2,737.08 per win
- **평균 손실**: -$1,626.09 per loss

## 전략 설명

### 진입 조건 (모두 만족해야 함)
1. **트렌드**: EMA(10) > EMA(30) (상승 추세)
2. **오버/언더슈팅**: RSI(14)가 20~80 범위 (극단값 제외)
3. **모멘텀**: MACD > Signal Line (상승 모멘텀)

### 청산 조건
1. **익절**: 진입가 대비 +7%
2. **손절**: ATR × 2.2만큼 아래
3. **Trailing Stop**: 최고가로부터 2% 하락
4. **EMA 교차**: EMA(10) < EMA(30) (하락 추세 전환)

### 포지션 크기
- 리스크: 계정 자산의 2%
- 진입량 = (2% × 계정자산) ÷ (진입가 - 손절가 거리)

## 설치 및 실행

### 사전 요구사항
```bash
pip install binance-connector
pip install pandas
pip install numpy
```

### 설정

**SecretVariables.py**에 Binance API 키 설정:
```python
BINANCE_API_KEY = "your_api_key"
BINANCE_API_SECRET = "your_api_secret"
```

### 실행

```bash
python3 eth_auto_trader.py
```

**주기**: 5분마다 4시간 봉 데이터 확인 및 신호 검사

## 코드 구조

### 클래스: `ETHAutoTrader`

#### 메서드

**`__init__()`**
- 전략 파라미터 초기화
- BetController 설정

**`calculate_atr(klines)`**
- ATR 지표 계산
- 손절매 거리 결정

**`calculate_ema(prices, period)`**
- EMA 지표 계산
- 트렌드 방향 판단

**`calculate_rsi(prices, period)`**
- RSI 지표 계산
- 과매수/과매도 필터링

**`calculate_macd(prices)`**
- MACD 및 Signal Line 계산
- 모멘텀 확인

**`check_signal(df)`**
- 매매 신호 판별
- Returns: (signal_type, signal_data)
  - signal_type: 'BUY', 'CLOSE', None
  - signal_data: 신호의 상세 정보

**`execute_trade(signal_type, signal_data)`**
- Binance Futures에 주문 실행
- 포지션 정보 저장/삭제
- Telegram 알림 발송

**`run()`**
- 메인 루프
- 데이터 수집 → 신호 판별 → 주문 실행

## 제한 사항 및 주의사항

### ⚠️ 중요
1. **단일 포지션만 가능** - 한 번에 1개의 ETH 포지션만 보유
2. **4시간 봉만 사용** - 더 짧은 시간대 신호는 사용 안 함
3. **현물처럼 거래** - 레버리지 1배 (손실 제한)

### 주의사항
1. **시장 갭**: 4시간 봉 마감 시간 근처에서만 신호 생성
   - Binance는 UTC 기준이므로 확인 필요
2. **네트워크 지연**: 주문 실행 시 지연 가능
3. **시간차**: API 응답까지 몇 초 지연 가능

### 리스크 관리
- 계정 자산의 2%만 위험 (risk_percent)
- 최대 손실: 한 거래당 -2%
- 최악의 경우: 10연속 손실 = -20% 드로우다운

## 파라미터 튜닝

백테스트 최적값이 이미 설정되어 있습니다:

```python
self.ema_short = 10      # 빠른 이동평균
self.ema_long = 30       # 느린 이동평균
self.rsi_overbuy = 80    # RSI 상한 (극단값)
self.rsi_oversell = 20   # RSI 하한 (극단값)
self.atr_multiplier = 2.2  # 손절 거리 배수
self.take_profit_pct = 0.07  # 익절 비율 (7%)
self.trailing_stop_pct = 0.02  # 트레일링 스탑 (2%)
```

**변경 전 백테스트 필수!**

## 모니터링

### 자동 알림 (Telegram)
- ✅ ETH 매수 신호
- ✅ ETH 매도 신호 (익절/손절/Trailing)
- ❌ 오류 및 네트워크 문제

### 로그
매 5분마다 다음이 출력됩니다:
```
[2024-02-15 10:23:00] ETH 자동매매 체크
📊 신호 감지: BUY
✅ ETH 매수 성공
   가격: $2,345.67
   수량: 0.42
   목표가: $2,509.27
   손절가: $2,247.34
   RSI: 45.3
   EMA: 2345.56 / 2340.23
```

## 문제 해결

### "충분한 데이터 없음"
- 원인: API가 100개 미만의 캔들 반환
- 해결: 네트워크 재연결 후 재시도

### "주문 실패"
- 원인: API 키 오류, 레버리지 설정 오류, 지갑 부족
- 해결:
  1. API 키/시크릿 확인
  2. Binance에서 수동으로 ETHUSDT 선물 활성화
  3. 레버리지 1배 설정 확인

### 포지션이 닫히지 않음
- 원인: 청산 신호 후 주문 실패
- 해결: Binance APP에서 수동으로 닫기

## 성능 비교 (다른 전략)

| 전략 | ROR | Sharpe | MDD | 승률 |
|------|-----|--------|-----|------|
| **OptimizedStrategy (현재)** | +91.71% | 0.64 | 25.85% | 42.0% |
| SDE Only | +1.01% | -2.42 | 1.95% | 33.3% |
| BollingerBand | ? | ? | ? | ? |
| TurtleStrategy | ? | ? | ? | ? |

> 데이터: ETH USDT 4시간 봉, 2021-01-01 ~ 2024-12-31

## 다음 개선 사항

- [ ] 여러 암호화폐 동시 거래
- [ ] 동적 포지션 사이징
- [ ] 시간대별 진입 필터 (특정 시간만 거래)
- [ ] 변동성 기반 stop loss 조정
- [ ] 머신러닝 기반 신호 필터

## 법적 고지

- 이 봇은 **과거 데이터 기반**이며 미래 수익을 보장하지 않습니다
- **자신의 책임 하에만 사용**하세요
- 손실 발생 시 개발자는 책임지지 않습니다
- Binance API Terms of Service를 준수하세요

## 참고 자료

- 백테스트 코드: `/backtest.py`
- 전략 구현: `/backtestStrategy/OptimizedStrategy.py`
- 데이터 수집: `/dataGenerator.py`

---

**작성일**: 2025-02-15  
**마지막 수정**: 2025-02-15  
**버전**: 1.0
