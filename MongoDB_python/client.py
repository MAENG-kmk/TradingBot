from SecretVariables import MONGODB_URI, COLLECTION
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import sys
import os
from datetime import datetime
sys.path.append(os.path.abspath("."))

uri = MONGODB_URI


def addDataToMongoDB(data):
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        database = client.get_database("Trade_History")
        collects = database.get_collection(COLLECTION)
        collects.insert_many(data)
        client.close()
    except Exception as e:
        raise Exception(
            "Unable to find the document due to the following error: ", e)


def addErrorCodeToMongoDB(data):
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        database = client.get_database("ErrorCode")
        collects = database.get_collection(COLLECTION)
        collects.insert_many(data)
        client.close()
    except Exception as e:
        raise Exception(
            "Unable to find the document due to the following error: ", e)


def addVersionAndDate(version, balance):
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        database = client.get_database("Version_History")
        collects = database.get_collection("history")

        # 가장 최근 버전과 동일하면 삽입하지 않음
        latest = collects.find_one(sort=[("date", -1)])
        if latest and latest.get("version") == version:
            client.close()
            return

        data = {
          'version': version,
          'date': datetime.now().timestamp(),
          'balance': balance,
        }
        collects.insert_one(data)
        client.close()
    except Exception as e:
        raise Exception(
            "Unable to find the document due to the following error: ", e)


def saveEntryDetails(symbol, mode, side, entry_price, candle_close_ts=None):
    """진입 시 상세 정보 저장 (프론트 hover 표시용 + 재시작 복구용)"""
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        db = client.get_database("Bot_Status")
        col = db.get_collection("open_positions")
        doc = {
            "symbol": symbol,
            "mode": mode,
            "side": side,
            "entry_price": entry_price,
            "enter_time": datetime.now().timestamp(),
        }
        if candle_close_ts is not None:
            doc["candle_close_ts"] = candle_close_ts
        col.update_one({"symbol": symbol}, {"$set": doc}, upsert=True)
        client.close()
    except Exception:
        pass


def getEntryDetails(symbol):
    """재시작 시 진입 기록 복구용"""
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        db = client.get_database("Bot_Status")
        col = db.get_collection("open_positions")
        doc = col.find_one({"symbol": symbol})
        client.close()
        return doc
    except Exception:
        return None


def deleteEntryDetails(symbol):
    """포지션 청산 시 진입 기록 삭제"""
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        db = client.get_database("Bot_Status")
        col = db.get_collection("open_positions")
        col.delete_one({"symbol": symbol})
        client.close()
    except Exception:
        pass


def updateHeartbeat():
    """하트비트 단일 문서 upsert — 매 사이클마다 호출"""
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        db = client.get_database("Bot_Status")
        col = db.get_collection("heartbeat")
        col.update_one(
            {"_id": "heartbeat"},
            {"$set": {"timestamp": datetime.now().timestamp()}},
            upsert=True,
        )
        client.close()
    except Exception:
        pass  # heartbeat 실패가 매매를 멈추면 안 됨
