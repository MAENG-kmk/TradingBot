from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import sys
import os
sys.path.append(os.path.abspath("."))
from SecretVariables import MONGODB_URI, COLLECTION

uri = MONGODB_URI

client = MongoClient(uri, server_api=ServerApi('1'))

def addDataToMongoDB(data):
    try:
        database = client.get_database("Trade_History")
        collects = database.get_collection(COLLECTION)
        collects.insert_many(data)
        client.close()
    except Exception as e:
        raise Exception("Unable to find the document due to the following error: ", e)

def addErrorCodeToMongoDB(data):
    try:
        database = client.get_database("ErrorCode")
        collects = database.get_collection(COLLECTION)
        collects.insert_many(data)
        client.close()
    except Exception as e:
        raise Exception("Unable to find the document due to the following error: ", e)