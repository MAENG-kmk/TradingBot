const { MongoClient } = require('mongodb');
require('dotenv').config();

const uri = process.env.MONGODB_URI;
const dbName = 'Trade_History';

let client;

const connectMongo = async () => {
  if (!client) {
    client = new MongoClient(uri);
    await client.connect();
  };

  return client.db(dbName)
};

const getCollection = async (collectionName) => {
  try {
    const db = await connectMongo();
    const cols = await db.listCollections().toArray();
    console.log(cols)
    return cols
  } catch(error) {
    console.log(error)
  }
};

module.exports = {
  getCollection,
};