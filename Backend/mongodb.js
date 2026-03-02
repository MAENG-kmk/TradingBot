const { MongoClient } = require('mongodb');
require('dotenv').config();

const uri = process.env.MONGODB_URI;

let client;

const connectMongo = async (dbName) => {
  if (!client) {
    client = new MongoClient(uri);
    await client.connect();
  };

  return client.db(dbName)
};

const getDocuments = async (dbName, collectionName) => {
  try {
    const db = await connectMongo(dbName);
    const collection = db.collection(collectionName);
    const documents = await collection.find({}).toArray();
    return documents;
  } catch (err) {
    console.log(err)
  }
};

const deleteVersion = async (versionId, versionName) => {
  try {
    // Version_History에서 해당 문서 삭제
    const versionDb = await connectMongo('Version_History');
    const { ObjectId } = require('mongodb');
    await versionDb.collection('history').deleteOne({ _id: new ObjectId(versionId) });
    // Trade_History에서 해당 컬렉션 삭제
    const tradeDb = await connectMongo('Trade_History');
    await tradeDb.collection(versionName).drop().catch(() => {});
  } catch (err) {
    console.log(err);
    throw err;
  }
};


module.exports = {
  getDocuments,
  deleteVersion,
};