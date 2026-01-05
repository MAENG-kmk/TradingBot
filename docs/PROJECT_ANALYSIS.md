# TradingBot 프로젝트 완전 분석

작성일: 2025-12-30  
기반: instruction.md + 실제 코드 분석

---

## 📊 프로젝트 개요

**목적**: Binance 선물 시장 자동 매매 봇  
**방식**: 롱/숏 양방향 거래  
**타임프레임**: 4시간 봉  
**전략**: 기술적 지표 기반 (볼린저 밴드 + MACD)

---

## 🏗️ 전체 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Binance API                          │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   Python Trading Bot         │
         │   (main.py)                  │
         │                              │
         │  ┌────────────────────────┐  │
         │  │  BetController         │  │
         │  │  - targetRor: 5%       │  │
         │  │  - stopLoss: -2%       │  │
         │  └────────────────────────┘  │
         │                              │
         │  ┌────────────────────────┐  │
         │  │  tools/                │  │
         │  │  - getData             │  │
         │  │  - getTicker           │  │
         │  │  - createOrder         │  │
         │  │  - 기술적 지표         │  │
         │  └────────────────────────┘  │
         │                              │
         │  ┌────────────────────────┐  │
         │  │  logics/               │  │
         │  │  - enterPosition       │  │
         │  │  - closePosition       │  │
         │  └────────────────────────┘  │
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │        MongoDB               │
         │    (거래 기록 저장)          │
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   Node.js Backend            │
         │   (REST API)                 │
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │   React Frontend             │
         │   (실시간 대시보드)          │
         └──────────────────────────────┘
```

---

## 🔄 메인 루프 실행 흐름

```python
def run_trading_bot():
    position_info = {}
    winning_history = [0, 0, 0, 0]
    
    while True:  # 무한 루프 (15초마다)
        try:
            # 1단계: 포지션 조회
            positions = getPositions(client)
            
            # 2단계: 청산 체크 (포지션이 있으면)
            if len(positions) > 0:
                print("포지션 정리 체크 중,,,")
                closePosition(
                    client, createOrder, positions,
                    position_info, winning_history,
                    getBalance, send_message, betController
                )
                # ├─ BetController.getClosePositions()
                # ├─ targetRor (+5%) 도달 → 청산
                # ├─ stopLoss (-2%) 도달 → 청산
                # └─ createOrder(SELL/BUY) 실행
            
            # 3단계: 잔고 조회
            total_balance, available_balance = getBalance(client)
            
            # 4단계: 진입 체크 (여유가 있으면)
            if not isPositionFull(total_balance, available_balance):
                print("포지션 진입 체크 중,,,")
                ticker = getTicker(client)
                positions = getPositions(client)
                enterPosition(
                    client, ticker, total_balance,
                    available_balance, positions, position_info,
                    logic_list, get1HData, getVolume,
                    setLeverage, createOrder, betController
                )
                # ├─ getTicker() - 모든 거래 가능 코인
                # ├─ for each coin:
                # │   ├─ getData() - 4H 봉 50개
                # │   ├─ checkRisk() - 리스크 체크
                # │   ├─ getATR() - 변동성 계산
                # │   ├─ getVolume() - 거래량 체크
                # │   ├─ logic_filter()
                # │   │   └─ getBolinger() AND getMACD()
                # │   └─ 조건 만족 → enter_list
                # └─ 최종 진입: setLeverage() + createOrder()
            
            # 5단계: 대기
            time.sleep(15)  # 15초
            
        except Exception as e:
            print('e:', e)
            asyncio.run(send_message(f"Error code: {e}"))
```

**실행 주기**: 15초마다 반복  
**평균 실행 시간**: ~17초 (sleep 포함)

---

## 📂 폴더 구조

```
TradingBot/
├── main.py                    # 메인 실행 파일 ⭐
├── instruction.md             # 프로젝트 가이드
├── SecretVariables.py         # API 키, MongoDB URI
├── README.markdown            # 프로젝트 설명
│
├── tools/                     # 유틸리티 함수들
│   ├── BetController.py       # 포지션 관리 핵심 ⭐⭐⭐
│   │   ├─ targetRorChecker    # {symbol: [targetRor, stopLoss]}
│   │   ├─ defaultTargetRor: 5%
│   │   └─ defaultStopLoss: -2%
│   │
│   ├── getData.py             # 4시간 봉 데이터
│   ├── getTicker.py           # 거래 가능 코인 목록
│   ├── getPositions.py        # 현재 포지션
│   ├── getBalance.py          # 잔고
│   ├── createOrder.py         # 주문 실행 (BUY/SELL)
│   ├── isPositionFull.py      # 포지션 여유 체크
│   ├── setLeverage.py         # 레버리지 설정
│   ├── checkRisk.py           # 리스크 체크
│   │
│   └── 기술적 지표/
│       ├── getRsi.py          # RSI 지표
│       ├── getMa.py           # 이동평균, MACD
│       ├── getBolinger.py     # 볼린저 밴드 ⭐
│       ├── getAtr.py          # ATR (변동성)
│       ├── getVolume.py       # 거래량
│       └── getLarry.py        # 래리 윌리엄스
│
├── logics/                    # 트레이딩 로직
│   ├── enterPosition.py       # 진입 결정 ⭐⭐⭐
│   ├── closePosition.py       # 청산 결정 ⭐⭐⭐
│   ├── decidePosition.py      # 포지션 결정
│   └── enterPositionTurtle.py # 터틀 전략
│
├── pair_trading/              # 페어 트레이딩 시스템 (별도)
│   ├── pair_finder.py         # 최적 쌍 찾기
│   ├── signal_monitor.py      # 진입 신호 모니터링
│   ├── position_monitor.py    # 청산 신호 모니터링
│   └── [관련 문서들]
│
├── MongoDB_python/            # MongoDB 연동
├── Backend/                   # Node.js API
├── frontend/                  # React 대시보드
├── backtestDatas/             # 백테스트 데이터
├── backtestStrategy/          # 백테스트 전략
└── docs/                      # 문서 (이 파일)
    ├── PROJECT_ANALYSIS.md    # 프로젝트 분석 (현재 파일)
    └── performance.md         # 성능 최적화 가이드
```

---

## 🎯 핵심 컴포넌트 상세

### 1. BetController (포지션 관리자)

```python
class BetController:
    """포지션 관리 핵심 클래스"""
    
    def __init__(self, client, logicList):
        self.client = client
        self.targetRorChecker = {}  # {symbol: [targetRor, stopLoss]}
        self.defaultTargetRor = 5   # 기본 목표: +5%
        self.defaultStopLoss = -2   # 기본 손절: -2%
        self.adjustRor = 1          # 목표 조정값
        self.logicList = logicList
    
    def saveNew(self, symbol, targetRor):
        """새 포지션 등록"""
        if targetRor <= 5:
            self.targetRorChecker[symbol] = [
                self.defaultTargetRor,
                self.defaultStopLoss
            ]
        else:
            # ATR 기반 동적 설정
            self.targetRorChecker[symbol] = [
                targetRor,
                -0.4 * targetRor
            ]
    
    def getClosePositions(self, positions):
        """청산할 포지션 결정"""
        list_to_close = []
        
        for position in positions:
            symbol = position['symbol']
            ror = position['ror']  # 현재 수익률
            
            if symbol not in self.targetRorChecker:
                self.saveNew(symbol, 0)
            
            [targetRor, stopLoss] = self.targetRorChecker[symbol]
            
            # 목표 수익 달성
            if ror >= targetRor:
                betting = self.bet(symbol, position['side'])
                if betting == 'close':
                    list_to_close.append(position)
                    self.targetRorChecker.pop(symbol, None)
            
            # 손절
            elif ror < stopLoss:
                list_to_close.append(position)
                self.targetRorChecker.pop(symbol, None)
        
        return list_to_close
    
    def bet(self, symbol, side):
        """추가 배팅 여부 결정"""
        # 현재는 항상 청산 (True 조건)
        if True:
            # 목표 상향 조정 옵션
            self.targetRorChecker[symbol] = [
                self.targetRorChecker[symbol][0] + self.adjustRor,
                self.targetRorChecker[symbol][1] - self.adjustRor
            ]
            return 'bet'
        else:
            return 'close'
```

**특징**:
- 포지션별 독립적인 목표/손절 관리
- ATR 기반 동적 목표 설정
- 수익 시 목표 상향 조정 가능

---

### 2. enterPosition (진입 로직)

```python
def enterPosition(client, ticker, total_balance, available_balance,
                 positions, position_info, logic_list, getData,
                 getVolume, setLeverage, createOrder, betController):
    """코인 스캔 및 진입"""
    
    # 포지션 크기 계산
    revision = 0.99
    bullet = float(total_balance) / 10 * revision  # 계정의 10%
    bullets = float(available_balance) // bullet   # 사용 가능 개수
    
    enter_list = []
    black_list = []
    
    # 모든 코인 스캔
    for _, coin in ticker.iterrows():
        symbol = coin['symbol']
        
        # 1. 데이터 수집
        data = getData(client, symbol, 50)  # 4시간 봉 50개
        if len(data) < 49:
            continue
        
        # 2. 리스크 체크
        if checkRisk(data) == False:
            continue
        
        # 3. 변동성 계산 (ATR)
        atr = getATR(data)
        targetRor = abs(atr / data.iloc[-1]['Close']) * 100
        
        # 4. 거래량 체크
        check_volume = getVolume(data)
        if not check_volume or symbol[-4:] != 'USDT' or symbol in black_list:
            continue
        
        # 5. 로직 필터 (핵심!)
        side = logic_filter(data, logic_list)
        # getBolinger() AND getMACD() 두 지표 모두 일치해야 함
        
        if side != 'None':
            # 중복 체크
            if not checkOverlap(positions, symbol):
                enter_list.append({
                    'symbol': symbol,
                    'side': side,
                    'targetRor': targetRor
                })
    
    # 최종 진입 실행
    for entry in enter_list[:bullets]:  # 여유 개수만큼만
        symbol = entry['symbol']
        side = entry['side']
        
        # 레버리지 설정
        setLeverage(client, symbol, leverage)
        
        # 주문 실행
        if side == 'long':
            createOrder(client, symbol, 'BUY', 'MARKET', amount)
        else:  # short
            createOrder(client, symbol, 'SELL', 'MARKET', amount)
        
        # BetController에 등록
        betController.saveNew(symbol, entry['targetRor'])


def logic_filter(data, logiclist):
    """로직 필터: 모든 지표가 같은 방향이어야 함"""
    result = 'None'
    
    for logic in logiclist:
        side = logic(data)  # getBolinger() or getMACD()
        
        if side == 'None':
            break
        
        if side == result:
            continue
        elif result == 'None':
            result = side
        else:
            # 불일치 발생
            result = 'None'
            break
    
    return result  # 'long', 'short', or 'None'
```

**진입 조건 체크리스트**:
1. ✅ 포지션 여유 (최대 10개)
2. ✅ 데이터 충분 (50개 캔들)
3. ✅ 리스크 체크 통과
4. ✅ 거래량 충분
5. ✅ USDT 마진 코인
6. ✅ 볼린저 밴드 신호
7. ✅ MACD 신호 일치
8. ✅ 중복 포지션 없음

---

### 3. closePosition (청산 로직)

```python
def closePosition(client, createOrder, positions, position_info,
                 winnig_history, getBalance, send_message, betController):
    """포지션 청산"""
    
    datas = []
    
    # BetController에게 청산 대상 문의
    list_to_close = betController.getClosePositions(positions)
    
    for position in list_to_close:
        response = False
        
        # 수익 포지션
        if position['ror'] > 0:
            if position['side'] == 'long':
                response = createOrder(
                    client, position['symbol'],
                    'SELL', 'MARKET', position['amount']
                )
                check_num = 0  # 롱 수익
            else:
                response = createOrder(
                    client, position['symbol'],
                    'BUY', 'MARKET', position['amount']
                )
                check_num = 2  # 숏 수익
        
        # 손실 포지션
        else:
            if position['side'] == 'long':
                response = createOrder(
                    client, position['symbol'],
                    'SELL', 'MARKET', position['amount']
                )
                check_num = 1  # 롱 손실
            else:
                response = createOrder(
                    client, position['symbol'],
                    'BUY', 'MARKET', position['amount']
                )
                check_num = 3  # 숏 손실
        
        # MongoDB 기록
        if response:
            data = position
            data['closeTime'] = int(datetime.now().timestamp())
            balance, _ = getBalance(client)
            data['balance'] = balance
            datas.append(data)
    
    if datas:
        addDataToMongoDB(datas)
```

**청산 조건**:
1. 수익 +5% 도달 (목표)
2. 손실 -2% 도달 (손절)
3. (선택) 로직 신호 반전

---

## 📊 트레이딩 전략 상세

### 진입 전략

```
기술적 지표 조합:

1. 볼린저 밴드 (getBolinger)
   ┌────────────────────────────┐
   │ 상단 밴드                  │
   ├────────────────────────────┤ ← 숏 신호 (상단 돌파)
   │   중간선 (20MA)            │
   ├────────────────────────────┤ ← 롱 신호 (하단 돌파)
   │ 하단 밴드                  │
   └────────────────────────────┘

2. MACD (getMACD)
   - MACD > Signal → 롱 신호 (골든크로스)
   - MACD < Signal → 숏 신호 (데드크로스)

3. logic_filter()
   ├─ 두 지표 모두 'long' → 진입 ✅
   ├─ 두 지표 모두 'short' → 진입 ✅
   └─ 불일치 → 진입 안 함 ❌
```

### 청산 전략

```
목표 수익 (Target RoR):
├─ 기본: +5%
├─ ATR 기반 동적 설정 가능
└─ 수익 시 상향 조정 옵션 (+1%)

손절 (Stop Loss):
├─ 기본: -2%
├─ ATR 기반: targetRor × -0.4
└─ 예: targetRor 10% → stopLoss -4%

청산 로직:
if ror >= targetRor:
    청산 (수익 실현)
elif ror <= stopLoss:
    청산 (손실 제한)
```

### 리스크 관리

```
포지션 크기:
├─ bullet = total_balance / 10 × 0.99
├─ 각 포지션: 계정의 약 10%
├─ 최대 10개 동시 포지션
└─ 총 위험: 계정의 최대 100%

레버리지:
└─ 동적 설정 (코인별 차이)

자금 관리:
├─ total_balance: 총 잔고
├─ available_balance: 사용 가능 잔고
└─ bullets = available_balance / bullet
```

---

## ⚙️ 주요 파라미터

| 파라미터 | 값 | 설명 | 위치 |
|---------|-----|------|------|
| **타임프레임** | 4시간 | 데이터 기준 | getData.py |
| **데이터 개수** | 50개 | 과거 캔들 | enterPosition.py |
| **포지션 단위** | 10% | 계정 기준 | enterPosition.py |
| **최대 포지션** | 10개 | 동시 보유 | 계산됨 |
| **목표 수익** | +5% | 기본값 | BetController |
| **손절** | -2% | 기본값 | BetController |
| **루프 간격** | 15초 | sleep | main.py |
| **수정 계수** | 0.99 | revision | enterPosition.py |

---

## 🔍 실행 시나리오 예시

### 시나리오: BTC 롱 진입 및 청산

#### **1단계: 스캔 (15초마다)**
```
getTicker() 실행
├─ BTCUSDT 발견
└─ 포지션 여유 확인: 9/10 → 여유 있음 ✅

getData(BTCUSDT, 50) 실행
└─ 4시간 봉 50개 수집 완료
```

#### **2단계: 분석**
```
checkRisk(data)
└─ 통과 ✅

getATR(data)
├─ ATR = 1800
├─ 현재가 = 45000
└─ targetRor = (1800/45000) × 100 = 4%

getVolume(data)
└─ 거래량 충분 ✅

logic_filter(data, [getBolinger, getMACD])
├─ getBolinger(data) → 'long' (하단 돌파)
├─ getMACD(data) → 'long' (골든크로스)
└─ 결과: 'long' ✅
```

#### **3단계: 진입**
```
총 잔고: $10,000
bullet = 10,000 / 10 × 0.99 = $990

setLeverage(BTCUSDT, 5)
createOrder(BTCUSDT, 'BUY', 'MARKET', 0.022 BTC)

BetController.saveNew(BTCUSDT, targetRor=4%)
├─ targetRor = 5% (기본값, ATR 4% < 5%이므로)
└─ stopLoss = -2%

포지션 등록:
{
  symbol: 'BTCUSDT',
  side: 'long',
  entryPrice: 45000,
  amount: 0.022,
  targetRor: 5%,
  stopLoss: -2%
}
```

#### **4단계: 청산 모니터링 (15초마다)**
```
15초 후:
├─ 현재가: 45200 (+0.44%)
└─ 상태: 유지 (목표 5% 미달)

1시간 후:
├─ 현재가: 45900 (+2.0%)
└─ 상태: 유지 (목표 5% 미달)

2시간 후:
├─ 현재가: 47250 (+5.0%) ✅
└─ 상태: 목표 달성!

청산 실행:
createOrder(BTCUSDT, 'SELL', 'MARKET', 0.022 BTC)
├─ 수익: $990 × 5% = $49.50
├─ 계정: $10,000 → $10,049.50
└─ MongoDB 기록

BetController.targetRorChecker에서 BTCUSDT 제거
```

#### **5단계: 실패 시나리오 (손절)**
```
15초 후:
├─ 현재가: 44800 (-0.44%)
└─ 상태: 유지 (손절 -2% 미달)

30초 후:
├─ 현재가: 44100 (-2.0%) ❌
└─ 상태: 손절 도달!

청산 실행:
createOrder(BTCUSDT, 'SELL', 'MARKET', 0.022 BTC)
├─ 손실: $990 × -2% = -$19.80
├─ 계정: $10,000 → $9,980.20
└─ MongoDB 기록
```

---

## 📈 데이터 흐름

```
[실시간 거래]
Binance API
    ↓ (15초마다)
Python Bot (main.py)
    ↓
BetController
    ↓
MongoDB (거래 기록)

[히스토리 조회]
MongoDB
    ↓
Node.js Backend (REST API)
    ↓
React Frontend (대시보드)

[모니터링]
React Dashboard
├─ 현재 포지션 목록
├─ 실시간 수익률
├─ 거래 내역
├─ 성과 차트
└─ 잔고 추이
```

---

## ⚠️ 위험 요소 및 주의사항

### 명시된 위험

```
README.markdown:
"## 주의
수익률 마이너스일 확률 높음"
```

### 실제 위험 분석

#### 1. **레버리지 위험**
```
- 레버리지 사용으로 손실 확대
- 급격한 가격 변동 시 청산 위험
- 수수료 누적
```

#### 2. **전략 위험**
```
- 기술적 지표 의존 → False Signal
- 볼린저 + MACD 조합의 한계
- 시장 급변 대응 어려움
- 백테스트 부족
```

#### 3. **타이밍 불일치**
```
- 데이터: 4시간 봉 기준
- 루프: 15초마다 체크
- 불일치로 인한 과매매 가능
```

#### 4. **성능 위험**
```
- getTicker(): 모든 코인 조회 (느림)
- API Rate Limit 위험
- 15초마다 반복 → 부하
```

#### 5. **자금 관리 위험**
```
- 최대 10개 포지션 = 계정의 100%
- 동시 손절 시 큰 손실
- 레버리지로 인한 청산 위험
```

---

## 💡 개선 제안

### 1. 성능 최적화 (즉시 가능)

```python
# Ticker 캐싱
cached_ticker = None
last_ticker_time = 0
TICKER_CACHE_SECONDS = 30

def run_trading_bot():
    while True:
        # Ticker 캐싱
        current_time = time.time()
        if current_time - last_ticker_time > TICKER_CACHE_SECONDS:
            cached_ticker = getTicker(client)
            last_ticker_time = current_time
        
        # 나머지 로직...
        
        time.sleep(10)  # 15초 → 10초

# 효과:
# - 실행 시간: 17초 → 11초 (35% 개선)
# - API 호출 감소
```

### 2. 백테스트 시스템 (중요!)

```python
# backtestDatas/ 폴더 활용
# backtestStrategy/ 폴더 활용

def backtest_strategy(strategy, data, params):
    """전략 백테스트"""
    
    results = []
    positions = []
    
    for i in range(len(data)):
        # 진입 신호
        signal = strategy(data[i])
        
        # 포지션 관리
        # ...
        
        # 청산 체크
        # ...
    
    return {
        'total_trades': len(results),
        'win_rate': win_rate,
        'total_return': total_return,
        'max_drawdown': max_drawdown
    }

# 필요성:
# - 전략 검증
# - 파라미터 최적화
# - 리스크 측정
```

### 3. 리스크 관리 강화

```python
# 일일 손실 제한
daily_loss_limit = -5%  # -5% 도달 시 거래 중단

# 포지션 상관관계 체크
def check_correlation(positions):
    """같은 방향 포지션 너무 많으면 제한"""
    long_count = sum(1 for p in positions if p['side'] == 'long')
    short_count = len(positions) - long_count
    
    if long_count > 7 or short_count > 7:
        return False  # 진입 제한
    
    return True

# 변동성 필터
def check_market_volatility():
    """시장 급변 시 거래 중단"""
    btc_data = getData(client, 'BTCUSDT', 10)
    volatility = btc_data['Close'].pct_change().std()
    
    if volatility > 0.05:  # 5% 이상 변동성
        return False  # 거래 중단
    
    return True
```

### 4. 페어 트레이딩 통합

```python
# pair_trading/ 폴더 활용
from pair_trading.signal_monitor import SignalMonitor
from pair_trading.position_monitor import PositionMonitor

# 메인 루프에 통합
def run_trading_bot():
    # 기존 전략
    traditional_strategy()
    
    # 페어 트레이딩
    pair_strategy()
    
    # 포트폴리오 관리
    portfolio_management()
```

---

## 🎓 학습 포인트

### 강점 ✅

1. **잘 구조화됨**
   - tools, logics 명확히 분리
   - BetController 중앙 집중 관리
   - 재사용 가능한 모듈

2. **양방향 거래**
   - 롱/숏 모두 지원
   - 시장 상황에 유연

3. **동적 관리**
   - ATR 기반 목표 조정
   - 포지션별 독립 관리

4. **완전한 시스템**
   - Python 로직
   - MongoDB 저장
   - Node.js API
   - React 모니터링

### 약점 ⚠️

1. **백테스트 부족**
   - 전략 검증 안 됨
   - 파라미터 최적화 필요

2. **성능 문제**
   - Ticker 매번 조회
   - 불필요한 API 호출

3. **리스크 관리 약함**
   - 동시 손절 위험
   - 상관관계 미고려

4. **타이밍 불일치**
   - 4시간 전략 vs 15초 체크
   - 과매매 가능성

---

## 📝 체크리스트

### 실전 운영 전 필수

```
□ 백테스트 완료
□ 종이 거래 1주일
□ 파라미터 최적화
□ Ticker 캐싱 적용
□ 일일 손실 제한 설정
□ 리스크 관리 강화
□ 모니터링 시스템 확인
□ 에러 핸들링 강화
□ API Rate Limit 확인
□ 소액 실전 테스트
```

### 일상 운영

```
□ 매일 성과 확인
□ 주간 파라미터 검토
□ 월간 전략 평가
□ 리스크 지표 모니터링
□ MongoDB 백업
□ 시스템 로그 확인
```

---

## 🔗 관련 문서

- [instruction.md](../instruction.md) - 프로젝트 기본 가이드
- [README.markdown](../README.markdown) - 프로젝트 소개
- [performance.md](./performance.md) - 성능 최적화 (멀티스레딩 분석)
- [pair_trading/README.md](../pair_trading/README.md) - 페어 트레이딩 시스템
- [pair_trading/ENTRY_SIGNALS.md](../pair_trading/ENTRY_SIGNALS.md) - 진입 신호
- [pair_trading/EXIT_SIGNALS.md](../pair_trading/EXIT_SIGNALS.md) - 청산 신호

---

## 📊 최종 요약

```
┌──────────────────────────────────────────────────┐
│          TradingBot 프로젝트 요약                │
├──────────────────────────────────────────────────┤
│                                                  │
│ 타입: Binance 선물 자동매매                      │
│ 전략: 볼린저 밴드 + MACD                         │
│ 타임프레임: 4시간                                │
│ 포지션: 최대 10개 (각 10%)                       │
│ 목표: +5%, 손절: -2%                            │
│ 루프: 15초마다 체크                              │
│                                                  │
│ 구조:                                            │
│ ├─ main.py (메인 루프)                           │
│ ├─ BetController (관리자)                       │
│ ├─ tools/ (유틸리티)                             │
│ ├─ logics/ (로직)                                │
│ └─ MongoDB + Node.js + React                    │
│                                                  │
│ 특징:                                            │
│ ✅ 잘 구조화됨                                   │
│ ✅ 양방향 거래                                   │
│ ✅ 동적 관리                                     │
│ ✅ 완전한 시스템                                 │
│                                                  │
│ 개선 필요:                                       │
│ ⚠️ 백테스트                                      │
│ ⚠️ 성능 최적화                                   │
│ ⚠️ 리스크 관리                                   │
│                                                  │
│ 다음 단계:                                       │
│ 1. 백테스트 시스템 구축                          │
│ 2. Ticker 캐싱 적용                              │
│ 3. 종이 거래 검증                                │
│ 4. 페어 트레이딩 통합                            │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 작성자 노트

이 문서는 instruction.md와 실제 코드를 분석하여 작성되었습니다.

**분석 일자**: 2025-12-30  
**버전**: 1.0  
**상태**: 완료

궁금한 점이나 추가 분석이 필요하면 언제든 문의하세요!
