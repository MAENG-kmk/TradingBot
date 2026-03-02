const express = require("express");
const cors = require("cors");
const dotenv = require("dotenv");
const { getDocuments, deleteVersion } = require("./mongodb");
const Binance = require("binance-api-node").default;

dotenv.config();
const PORT = process.env.PORT || 3000;

const app = express();

app.use(cors({ 
  origin: ["http://localhost:3000", "https://trading-bot-black.vercel.app"],
  methods: ["GET", "POST", "DELETE"],
  credentials: true }));

const client = Binance({
  apiKey: process.env.BINANCE_API_KEY,
  apiSecret: process.env.BINANCE_API_SECRET,
});

app.set("port", PORT);

app.get("/balance", async (req, res) => {
  try {
    const balances = await client.futuresAccountBalance();
    var usdt = "";
    balances.forEach((balance) => {
      if (balance["asset"] == "USDT") {
        usdt = balance["balance"];
      }
    });

    res.json({
      success: true,
      balance: usdt,
    });
  } catch (err) {
    console.error("Error fetching balance:", err);
    res.status(500).json({
      success: false,
      message: "Failed to fetch balance",
      error: err.message,
    });
  }
});

app.get("/currentVersion", async (req, res) => {
  try {
    const versionAndDate = await getDocuments('Version_History', 'history');
    const lastData = versionAndDate.pop();
    const version = lastData.version;
    const date = lastData.date;
    const balance = lastData.balance;

    res.json({
      success: true,
      version: version,
      date: date,
      balance: balance,
    })
  } catch (err) {
    console.log(err);
  }
});

app.get("/datas", async (req, res) => {
  try {
    const collectionName = req.query.collection;
    const datas = await getDocuments('Trade_History', collectionName);

    res.json({
      success: true,
      datas: datas,
    })
  } catch (err) {
    console.log(err);
  }
});

app.get("/versionDatas", async (req, res) => {
  try {
    const datas = await getDocuments('Version_History', 'history');

    res.json({
      success: true,
      datas: datas,
    })
  } catch (err) {
    console.log(err);
  }
});

app.get("/positions", async (req, res) => {
  try {
    const datas = (await client.futuresAccountInfo()).positions;
    const openPositions = datas.filter(pos => parseFloat(pos.positionAmt) !== 0);
    res.json({
      success: true,
      datas: openPositions,
    })
  } catch (err) {
    console.log(err);
  }
});

app.delete("/version", async (req, res) => {
  try {
    const { id, version } = req.query;
    if (!id || !version) {
      return res.status(400).json({ success: false, message: "id and version required" });
    }
    await deleteVersion(id, version);
    res.json({ success: true });
  } catch (err) {
    console.log(err);
    res.status(500).json({ success: false, message: err.message });
  }
});

app.listen(app.get("port"), () => {
  console.log(app.get("port"), "번 포트에서 대기 중");
});
