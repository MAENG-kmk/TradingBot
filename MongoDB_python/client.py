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


def addVersionAndDate(version):
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        database = client.get_database("Version_History")
        collects = database.get_collection("history")
        data = {
          'version': version,
          'date': datetime.now().timestamp()
        }
        collects.insert_one(data)
        client.close()
    except Exception as e:
        raise Exception(
            "Unable to find the document due to the following error: ", e)
