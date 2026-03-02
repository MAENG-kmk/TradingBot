import { useEffect, useState, useMemo } from 'react'
import styles from './Main.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import CoinComparisonChart from '../../components/Graph/CoinComparisonChart';
import { useNavigate } from 'react-router-dom';

const COINS = ['ALL', 'ETH', 'BTC', 'SOL', 'BNB', 'XRP', 'LINK', 'DOGE', 'AVAX', 'ARB', 'AAVE'];

const Main = () => {
  const [startBalance, setStartBalance] = useState('');
  const [balance, setBalance] = useState('');
  const [pnl, setPnl] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [positionDatas, setPositionDatas] = useState([]);
  const [selectedCoin, setSelectedCoin] = useState('ALL');

  const navigate  = useNavigate();

  useEffect(() => {
    const getDatas = async () => {
      try {
        const response_0 = await axios.get(`${process.env.REACT_APP_API_URL}/balance`);
        if (response_0.data.success) {
          setBalance(parseFloat(response_0.data.balance).toFixed(2));
        };

        const response = await axios.get(`${process.env.REACT_APP_API_URL}/currentVersion`);
        if (response.data.success) {
          const vers = response.data.version;
          const sb = response.data.balance;
          setStartBalance(sb);
          setVersion(vers);

          const positions = await axios.get(`${process.env.REACT_APP_API_URL}/positions`);
          if (positions.data.success) {
            const curPosition = positions.data.datas;
            const positionList = curPosition.map((data) => {
              const ror = (parseFloat(data.unrealizedProfit) / parseFloat(data.positionInitialMargin) * 100).toFixed(2);
              const side = parseFloat(data.positionAmt) > 0 ? 'long' : 'short';
              const cur = {
                symbol: data.symbol,
                ror: ror,
                side: side,
              };
              return cur;
            });
            setPositionDatas(positionList);
          };

          const incodig = encodeURIComponent(vers);
          const response_2 = await axios.get(`${process.env.REACT_APP_API_URL}/datas?collection=${incodig}`);
          if (response_2.data.success) {
            const messData = response_2.data.datas;
            const processed = messData.map(data => {
              const filter = {};
              const convertedDate = formatTimestamp(data.closeTime);
              filter['name'] =  convertedDate;
              filter['symbol'] = data.symbol;
              filter['enterTime'] = formatTimestamp(data.enterTime);
              filter['Profit'] = parseFloat(data.profit).toFixed(2);
              filter['balance'] = parseFloat(data.balance).toFixed(2);
              filter['side'] = data.side;

              return filter;
            });
            setPnl((parseFloat(response_0.data.balance)-parseFloat(sb)).toFixed(2))
            setBalanceDatas(processed);
            setPnlDatas(processed);
          };
        }
      } catch (error) {
        console.log(error)
      }
    };

    getDatas();
  }, [])

  // 코인별 필터링
  const filteredBalanceDatas = useMemo(() => {
    if (selectedCoin === 'ALL') return balanceDatas;
    return balanceDatas.filter(d => d.symbol === selectedCoin + 'USDT');
  }, [balanceDatas, selectedCoin]);

  const filteredPnlDatas = useMemo(() => {
    if (selectedCoin === 'ALL') return pnlDatas;
    return pnlDatas.filter(d => d.symbol === selectedCoin + 'USDT');
  }, [pnlDatas, selectedCoin]);

  const filteredPositions = useMemo(() => {
    if (selectedCoin === 'ALL') return positionDatas;
    return positionDatas.filter(d => d.symbol === selectedCoin + 'USDT');
  }, [positionDatas, selectedCoin]);

  const filteredPnl = useMemo(() => {
    if (selectedCoin === 'ALL') return pnl;
    const total = filteredPnlDatas.reduce((sum, d) => sum + parseFloat(d.Profit), 0);
    return total.toFixed(2);
  }, [selectedCoin, pnl, filteredPnlDatas]);

  // 코인별 손익 비교 데이터
  const coinSummary = useMemo(() => {
    const map = {};
    pnlDatas.forEach(d => {
      const coin = d.symbol ? d.symbol.replace('USDT', '') : 'UNKNOWN';
      if (!map[coin]) map[coin] = { coin, profit: 0, trades: 0, wins: 0 };
      map[coin].profit += parseFloat(d.Profit);
      map[coin].trades += 1;
      if (parseFloat(d.Profit) > 0) map[coin].wins += 1;
    });
    return Object.values(map)
      .map(c => ({
        ...c,
        profit: parseFloat(c.profit.toFixed(2)),
        winRate: c.trades > 0 ? (c.wins / c.trades * 100).toFixed(1) : '0.0',
      }))
      .sort((a, b) => b.profit - a.profit);
  }, [pnlDatas]);

  const handleClickButton = () => {
    navigate('/history');
  };

  const handlePositionClick = (symbol) => {
    window.open(`https://www.binance.com/en/futures/${symbol}`, '_blank');
  };

  const handleCoinTabClick = (coin) => {
    setSelectedCoin(coin);
  };

  return(
    <div className={styles.background}>
      <div className={styles.headerContainer}>
        <div className={styles.titleContainer}>
          <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
          <div className={styles.modelName}>Current Model : {version}</div>
        </div>
        <button className={styles.button} onClick={handleClickButton}>Model History</button>
      </div>

      {/* 코인 탭 */}
      <div className={styles.coinTabs}>
        {COINS.map(coin => (
          <button
            key={coin}
            className={`${styles.coinTab} ${selectedCoin === coin ? styles.coinTabActive : ''}`}
            onClick={() => handleCoinTabClick(coin)}
          >
            {coin}
          </button>
        ))}
      </div>

      <div className={styles.row}>
        <div className={`${styles.assetContent} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.name}>{selectedCoin === 'ALL' ? 'Asset Value' : `${selectedCoin} Trades`}</div>
            <div className={styles.balance}><span className={styles.label}>Current Asset :</span>{balance} $</div>
          </div>
          <div className={styles.graph}>
            <LineGraph datas={filteredBalanceDatas} />
          </div>
        </div>
        <div className={`${styles.rorContent} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.statistics}>Current Position</div>
          </div>
          {filteredPositions.map((position) => {
            return(
              <div className={styles.position} key={position.symbol} onClick={() => {handlePositionClick(position.symbol)}}>
                <div>{position.symbol}<span>{position.side}</span></div>
                <div style={position.ror > 0 ? {color: 'rgb(35, 255, 35)'} : {color: '#F44336'}}>{position.ror}%</div>
              </div>
            )
          })}
        </div>
      </div>
      <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
        <div className={styles.header}>
          <div className={styles.name}>{selectedCoin === 'ALL' ? 'Profit and Loss ($)' : `${selectedCoin} P&L ($)`}</div>
          <div className={filteredPnl > 0 ? styles.plus : styles.minus}>
            <span className={styles.label}>Total :</span>
            {filteredPnl} $
            {selectedCoin === 'ALL' && startBalance ? ` ( ${(pnl/startBalance*100).toFixed(2)} % )` : ''}
          </div>
        </div>
        <div className={styles.graph}>
          <BarGraph datas={filteredPnlDatas} />
        </div>
      </div>

      {/* 코인별 손익 비교 차트 */}
      {selectedCoin === 'ALL' && coinSummary.length > 0 && (
        <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.name}>Coin Performance</div>
          </div>
          <div className={styles.graph}>
            <CoinComparisonChart datas={coinSummary} onCoinClick={(coin) => handleCoinTabClick(coin)} />
          </div>
        </div>
      )}
    </div>
  )
}

export default Main