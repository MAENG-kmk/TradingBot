import { useEffect, useState, useMemo } from 'react'
import styles from './Main.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import CandlestickChart from '../../components/Graph/CandlestickChart';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import CoinComparisonChart from '../../components/Graph/CoinComparisonChart';
import { useNavigate } from 'react-router-dom';

const COINS = ['ALL', 'ETH', 'SUI', 'SOL', 'BNB', 'XRP', 'LINK', 'DOGE', 'AVAX', 'ARB', 'AAVE'];

const Main = () => {
  const [startBalance, setStartBalance] = useState('');
  const [balance, setBalance] = useState('');
  const [pnl, setPnl] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [positionDatas, setPositionDatas] = useState([]);
  const [selectedCoin, setSelectedCoin] = useState('ALL');
  const [botStatus, setBotStatus] = useState({ alive: null, minutesAgo: null });
  const [candleData, setCandleData] = useState([]);
  const [entryDetails, setEntryDetails] = useState({});

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
                entryPrice: parseFloat(data.entryPrice).toFixed(4),
              };
              return cur;
            });
            setPositionDatas(positionList);
          };

          const entryRes = await axios.get(`${process.env.REACT_APP_API_URL}/entry-details`);
          if (entryRes.data.success) {
            const map = {};
            entryRes.data.datas.forEach(d => { map[d.symbol] = d; });
            setEntryDetails(map);
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

    const checkHeartbeat = async () => {
      try {
        const res = await axios.get(`${process.env.REACT_APP_API_URL}/heartbeat`);
        if (res.data.success) {
          setBotStatus({ alive: res.data.alive, minutesAgo: res.data.minutesAgo });
        }
      } catch {
        setBotStatus({ alive: false, minutesAgo: null });
      }
    };

    getDatas();
    checkHeartbeat();
    const interval = setInterval(checkHeartbeat, 60000);
    return () => clearInterval(interval);
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

  // 캔들차트 마커용 트레이드 데이터 (timestamp → unix seconds)
  const candleTrades = useMemo(() => {
    if (selectedCoin === 'ALL') return [];
    return filteredPnlDatas.map(d => {
      const parseDate = (str) => {
        if (!str) return null;
        const date = new Date(str);
        if (isNaN(date.getTime())) return null;
        return Math.floor(date.getTime() / 1000);
      };
      return {
        enterTimestamp: parseDate(d.enterTime),
        closeTimestamp: parseDate(d.name),
        side: d.side,
        Profit: d.Profit,
      };
    }).filter(d => d.enterTimestamp || d.closeTimestamp);
  }, [filteredPnlDatas, selectedCoin]);

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

  const handleCoinTabClick = async (coin) => {
    setSelectedCoin(coin);
    if (coin !== 'ALL') {
      try {
        const res = await axios.get(
          `${process.env.REACT_APP_API_URL}/klines?symbol=${coin}USDT&interval=1h&limit=200`
        );
        if (res.data.success) {
          setCandleData(res.data.datas);
        }
      } catch (err) {
        console.log('Failed to fetch klines:', err);
        setCandleData([]);
      }
    } else {
      setCandleData([]);
    }
  };

  return(
    <div className={styles.background}>
      <div className={styles.headerContainer}>
        <div className={styles.titleContainer}>
          <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
          <div className={styles.modelName}>
            Current Model : {version}
            <span className={`${styles.heartbeat} ${
              botStatus.alive === null ? styles.loading :
              botStatus.alive ? styles.alive : styles.dead
            }`}>
              {botStatus.alive === null ? '⏳' : botStatus.alive ? '🟢 BOT ALIVE' : '🔴 BOT DOWN'}
              {botStatus.minutesAgo !== null && ` (${botStatus.minutesAgo}m ago)`}
            </span>
          </div>
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
            <div className={styles.name}>{selectedCoin === 'ALL' ? 'Asset Value' : `${selectedCoin}/USDT`}</div>
            <div className={styles.balance}><span className={styles.label}>Current Asset :</span>{balance} $</div>
          </div>
          <div className={styles.graph}>
            {selectedCoin === 'ALL' ? (
              <LineGraph datas={filteredBalanceDatas} />
            ) : (
              <CandlestickChart candles={candleData} trades={candleTrades} />
            )}
          </div>
        </div>
        <div className={`${styles.rorContent} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.statistics}>Current Position</div>
          </div>
          {filteredPositions.map((position) => {
            const detail = entryDetails[position.symbol];
            const modeLabel = {
              'trend_following': '✅ 추세추종 (TR)',
              'mean_reversion':  '📊 평균회귀 (MR)',
              'vb':              '📈 변동성 돌파 (VB)',
              'vb_close':        '📈 변동성 돌파 (VB)',
              'sde':             '🔬 GBM 확률 (SDE)',
            }[detail?.mode] || '—';
            const enterTimeStr = detail?.enter_time
              ? new Date(detail.enter_time * 1000).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
              : '—';
            return(
              <div className={styles.positionWrapper} key={position.symbol}>
                <div className={styles.position} onClick={() => {handlePositionClick(position.symbol)}}>
                  <div>{position.symbol}<span>{position.side}</span></div>
                  <div style={position.ror > 0 ? {color: 'rgb(35, 255, 35)'} : {color: '#F44336'}}>{position.ror}%</div>
                </div>
                <div className={styles.positionTooltip}>
                  <div className={styles.tooltipRow}><span className={styles.tooltipLabel}>진입 시각</span><span>{enterTimeStr}</span></div>
                  <div className={styles.tooltipRow}><span className={styles.tooltipLabel}>진입 전략</span><span>{modeLabel}</span></div>
                  <div className={styles.tooltipRow}><span className={styles.tooltipLabel}>진입가</span><span>{position.entryPrice}</span></div>
                </div>
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