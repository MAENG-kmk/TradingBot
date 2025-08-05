# Crypto Auto-Trading Bot

## 프로젝트 소개
Binance 선물 시장에서 `python-binance`를 활용한 암호화폐 자동 매매 봇. 롱/숏 양방향 매매를 지원하며, 실시간 데이터 기반 트레이딩 제공.

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