const express = require("express");
const cors = require("cors");
const dotenv = require("dotenv");
const { getCollection } = require("./mongodb");
const Binance = require("binance-api-node").default;

dotenv.config();
const PORT = process.env.PORT || 3000;

const app = express();

app.use(cors({ origin: "http://localhost:3000" }));

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

app.get("/test", async (req, res) => {
  try {
    const a = await getCollection();
    console.log(a);

    res.json({
      db: a,
    })
  } catch (err) {
    console.log(err);
  }
});

app.listen(app.get("port"), () => {
  console.log(app.get("port"), "번 포트에서 대기 중");
});
