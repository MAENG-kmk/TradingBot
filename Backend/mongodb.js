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


module.exports = {
  getDocuments,
};