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
- **로직**: Python (`python-binance`, `pandas`)
- **프론트엔드**: React (`chart.js`, `axios`)
- **백엔드**: Node.js (`express`, `mongoose`)
- **DB**: MongoDB

## 설치
1. 클론: `git clone https://github.com/yourusername/crypto-auto-trading-bot.git`
2. 백엔드: `cd backend && npm install`
3. 프론트엔드: `cd frontend && npm install`
4. Python: `cd logic && pip install -r requirements.txt`
5. `.env` 설정:
   ```
   BINANCE_API_KEY=your_api_key
   BINANCE_SECRET_KEY=your_secret_key
   MONGODB_URI=mongodb://localhost:27017/crypto_bot
   ```

## 사용법
1. 백엔드: `cd backend && npm start`
2. Python 봇: `cd logic && python main.py`
3. 프론트엔드: `cd frontend && npm start` (http://localhost:3000)

## 기여
1. 이슈 생성
2. 포크 후 브랜치: `git checkout -b feature/xxx`
3. 커밋 및 PR

## 라이선스
MIT License

## 주의
교육용 프로젝트. 실제 트레이딩 시 자본 손실 위험 있음.