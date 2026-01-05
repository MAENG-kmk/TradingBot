# 페어 트레이딩 전략 적용 가이드

## 📊 변경 사항 요약

**기존**: 모든 코인을 스캔하여 볼린저 밴드 + MACD 신호로 개별 진입  
**변경**: 페어 쌍을 찾아 Z-Score 기반으로 롱/숏 동시 진입

---

## 🚀 빠른 시작

### 1단계: 페어 찾기 (최초 1회)

```bash
cd pair_trading
source ../myvenv/bin/activate
python pair_finder.py
```

결과:
- `pair_trading_results.json` 생성 (5개 페어)
- 이 파일이 있어야 진입 가능

### 2단계: 메인 파일 교체

#### Option A: 기존 파일 백업 후 교체 (권장)

```bash
# 기존 main.py 백업
mv main.py main_original.py

# 페어 트레이딩 버전을 main.py로
cp main_pair_trading.py main.py

# 또는 직접 사용
python main_pair_trading.py
```

#### Option B: 기존 main.py 수정

```python
# main.py 상단에 추가
from logics.enterPositionPairTrading import enterPositionPairTrading

# run_trading_bot() 함수 내 enterPosition 호출 부분을 교체
# 기존:
# ticker = getTicker(client)
# enterPosition(client, ticker, total_balance, available_balance, 
#              positions, position_info, logic_list, get4HData, 
#              getVolume, setLeverage, createOrder, betController)

# 변경:
enterPositionPairTrading(
    client=client,
    total_balance=total_balance,
    available_balance=available_balance,
    positions=positions,
    position_info=position_info,
    setLeverage=setLeverage,
    createOrder=createOrder,
    betController=betController,
    zscore_threshold=2.5
)
```

---

## 📂 새로 생성된 파일

```
logics/
└── enterPositionPairTrading.py  ← 페어 트레이딩 진입 로직

main_pair_trading.py             ← 페어 트레이딩용 main.py
```

---

## 🔄 실행 흐름 비교

### 기존 방식
```
while True (15초):
  1. getPositions()
  2. closePosition()
  3. getBalance()
  4. getTicker() ← 모든 코인 조회
  5. for each coin:
       - getBolinger()
       - getMACD()
       - 신호 일치 시 진입
  6. sleep(15)
```

### 페어 트레이딩 방식
```
while True (15초):
  1. getPositions()
  2. closePosition()
  3. getBalance()
  4. pair_trading_results.json 로드
  5. for each pair:
       - Z-Score 계산
       - Z > 2.5 또는 Z < -2.5
       - 신호 시 페어 동시 진입
         (Coin1 롱 + Coin2 숏)
  6. sleep(15)
```

---

## ⚙️ 설정 가능한 파라미터

### enterPositionPairTrading() 함수

```python
enterPositionPairTrading(
    client=client,
    total_balance=total_balance,
    available_balance=available_balance,
    positions=positions,
    position_info=position_info,
    setLeverage=setLeverage,
    createOrder=createOrder,
    betController=betController,
    zscore_threshold=2.5  # ← 조정 가능
)
```

**zscore_threshold 조정**:
- `2.0`: 더 자주 진입 (공격적)
- `2.5`: 균형 (기본값) ⭐
- `3.0`: 덜 자주 진입 (보수적)

---

## 📊 진입 예시

### 시나리오: ETH + SOL 페어

```
pair_trading_results.json:
{
  "symbol1": "ETHUSDT",
  "symbol2": "SOLUSDT",
  "hedge_ratio": 15.60,
  "correlation": 0.8881
}

현재 상황:
- ETH: $3,700 (과대평가)
- SOL: $200
- Z-Score: +2.8 🔴

진입 신호: 롱 스프레드
- ETHUSDT: 롱 (Long)
- SOLUSDT: 숏 (Short)

포지션 크기:
- bullet = 계정 / 10 = $1,000
- 각 코인: $500씩 (bullet / 2)

실제 주문:
- ETH 롱: $500 / 3700 = 0.135 ETH
- SOL 숏: $500 / 200 = 2.5 SOL
```

---

## 🎯 진입 조건

### 필수 조건 (모두 만족)

```
✅ pair_trading_results.json 존재
✅ 포지션 여유 (페어는 2개 포지션 차지)
✅ |Z-Score| > 2.5 (기본값)
✅ 상관관계 > 0.75 (실시간 재확인)
✅ 페어 중복 없음
```

### 진입 신호

```
Z-Score > +2.5:
  → 롱 스프레드
  → Coin1 롱 + Coin2 숏

Z-Score < -2.5:
  → 숏 스프레드
  → Coin1 숏 + Coin2 롱
```

---

## 🔍 position_info 구조 변경

### 기존
```python
position_info[symbol] = [side, 0]
# 예: position_info['BTCUSDT'] = ['long', 0]
```

### 페어 트레이딩
```python
position_info[symbol] = [side, zscore, 'pair', pair_symbol]
# 예:
# position_info['ETHUSDT'] = ['long', 2.8, 'pair', 'SOLUSDT']
# position_info['SOLUSDT'] = ['short', 2.8, 'pair', 'ETHUSDT']
```

이를 통해:
- 페어임을 표시 (`'pair'`)
- 진입 시 Z-Score 기록
- 페어 상대방 심볼 저장

---

## ⚠️ 주의사항

### 1. 페어 파일 필수
```bash
# 페어 파일이 없으면 진입 안 됨
# 최초 1회 실행 필수:
cd pair_trading
python pair_finder.py
```

### 2. 포지션 개수
```
기존: 최대 10개 개별 포지션
변경: 최대 5개 페어 (= 10개 포지션)

1 페어 = 2 포지션
```

### 3. 목표/손절
```
현재: 개별 코인 기준 (+5% / -2%)
이상적: 스프레드 기준 (향후 개선)

⚠️ 개별 코인 수익률과 스프레드 수익률은 다름!
```

### 4. 청산 로직
```
closePosition.py는 그대로 사용
하지만 페어를 함께 청산하도록 개선 필요 (향후)

현재: 개별 청산 (한쪽만 청산 가능)
이상적: 페어 동시 청산
```

---

## 📈 성능 비교 예상

### 기존 방식
```
진입 빈도: 높음 (매일 여러 번)
수익률: 변동성 높음
리스크: 방향성 위험 (시장 급락 시 손실)
복잡도: 낮음
```

### 페어 트레이딩
```
진입 빈도: 낮음 (주 1~2회)
수익률: 안정적 (목표: 월 5~10%)
리스크: 낮음 (헤징으로 방향성 위험 제거)
복잡도: 높음
```

---

## 🔧 문제 해결

### Q: "페어 파일 없음" 에러

```bash
# pair_finder.py 실행
cd pair_trading
source ../myvenv/bin/activate
python pair_finder.py
```

### Q: "진입 신호 없음"

```
원인:
1. 모든 페어의 Z-Score가 임계값 미달
2. 상관관계 붕괴 (< 0.75)

해결:
1. zscore_threshold 낮추기 (2.5 → 2.0)
2. 페어 새로 찾기 (pair_finder.py 재실행)
```

### Q: 한쪽만 청산됨

```
현재 버전의 한계:
- closePosition.py는 개별 청산
- 페어 동시 청산 미구현

임시 해결:
- 수동으로 나머지 청산
- 또는 목표/손절 도달 대기

향후 개선:
- closePositionPairTrading.py 구현 필요
```

---

## 📝 체크리스트

### 실행 전

```
□ pair_finder.py 실행 완료
□ pair_trading_results.json 확인
□ 5개 페어 로드 확인
□ 기존 main.py 백업
□ main_pair_trading.py 테스트
```

### 실행 중

```
□ 페어 진입 로그 확인
□ 양쪽 포지션 모두 생성 확인
□ position_info 구조 확인
□ Z-Score 변화 모니터링
```

### 문제 발생 시

```
□ pair_trading_results.json 존재 확인
□ Binance API 연결 확인
□ 에러 로그 확인
□ 기존 main_original.py로 복구
```

---

## 🎓 다음 단계

### 즉시 구현
1. ✅ 페어 진입 로직 (완료)
2. 🔲 페어 청산 로직 (필요)
3. 🔲 백테스트 시스템

### 향후 개선
1. 스프레드 기준 목표/손절
2. 페어 동시 청산
3. 복수 전략 운영 (기존 + 페어)
4. 웹 대시보드 페어 표시

---

## 작성일
2026-01-01

## 상태
✅ 진입 로직 구현 완료  
⚠️ 청산 로직 개선 필요  
🔲 백테스트 필요
