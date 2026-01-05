가상환경: myvenv

main.py -> 실행 파일

client -> main.py에서 생성 후 필요한 함수마다 인자로 보내줌.

tools -> 도구 모음

getData.py -> get4HData(client, symbol, limit) 사용

createOrder.py -> 매수, 매도 함수. 매수: side=BUY, 매도: side=SELL, type=MARKET

getPosition.py -> 현재 포지션 가져오기

getBalance.py -> 현재 잔고 가져오기

logics -> 포지션 진입, 종료 관련 파일들 폴더

enterPosition.py -> 포지션 진입 결정

closePosition.py -> 포지션 정리 결정