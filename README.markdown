# Crypto Auto-Trading Bot

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

## 주요 기능
- Binance 선물 시장 매매 (BTCUSDT, ETHUSDT 등)
- 사용자 정의 트레이딩 전략 (Python)
- React 대시보드로 실시간 모니터링
- Node.js 백엔드 API
- MongoDB로 트레이딩 데이터 저장

## 기술 스택
- **로직**: Python 
- **프론트엔드**: React
- **백엔드**: Node.js 
- **DB**: MongoDB

## SecretVariables 변수 설정
   ```
   BINANCE_API_KEY=your_api_key
   BINANCE_API_SECRET=your_secret_key
   MONGODB_URI=your_mongodb_uri
   COLLECTION=collection name at your database
   ```

## 사용법
1. 백엔드: `cd backend && npm start`
2. Python 봇: `cd logic && python main.py`
3. 프론트엔드: `cd frontend && npm start` (http://localhost:3000)

## 주의
수익률 마이너스일 확률 높음

