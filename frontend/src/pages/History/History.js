import { useEffect, useState, useMemo } from 'react'
import styles from './History.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import PieGraph from '../../components/Graph/PieGraph';
import CoinComparisonChart from '../../components/Graph/CoinComparisonChart';
import AnalyticsReport from '../../components/Graph/AnalyticsReport';
import { useNavigate } from 'react-router-dom';

const COINS = ['ALL', 'ETH', 'BTC', 'SOL', 'BNB', 'XRP', 'LINK', 'DOGE', 'AVAX', 'ARB', 'AAVE'];

const History = () => {
  const [versionDatas, setVersionDatas] = useState([]);
  const [startBalance, setStartBalance] = useState('');
  const [date, setDate] = useState('');
  const [pnl, setPnl] = useState(0);
  const [numTrade, setNumTrade] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [, setWinningRateData] = useState([]);
  const [selectedCoin, setSelectedCoin] = useState('ALL');

  const navigate  = useNavigate();

  useEffect(() => {
    const getVersions = async () => {
      try {
        const response = await axios.get(`${process.env.REACT_APP_API_URL}/versionDatas`);
        if (response.data.success) {
          const datas = response.data.datas;
          setVersionDatas(datas);
        }
      } catch (err) {
        console.log(err);
      }
    };

    const getDatas = async () => {
      try {
        if (version) {
          const incodig = encodeURIComponent(version);
          const response_2 = await axios.get(`${process.env.REACT_APP_API_URL}/datas?collection=${incodig}`);
          if (response_2.data.success) {
            const messData = response_2.data.datas;
            setNumTrade(messData.length);
            var win = 0;
            var lose = 0;
            const balances = [];
            const processed = messData.map(data => {
              const filter = {};
              const convertedDate = formatTimestamp(data.closeTime);
              balances.push({
                name: convertedDate,
                Balance: parseFloat(data.balance).toFixed(2),
              })
              filter['name'] =  convertedDate;
              filter['symbol'] = data.symbol;
              filter['enterTime'] = formatTimestamp(data.enterTime);
              filter['rawEnterTime'] = data.enterTime;
              filter['rawCloseTime'] = data.closeTime;
              filter['Profit'] = parseFloat(data.profit).toFixed(2);
              filter['balance'] = parseFloat(data.balance).toFixed(2);
              filter['side'] = data.side;
              filter['ror'] = data.ror;
              if (data.ror > 0) {
                win += 1;
              } else {
                lose += 1;
              };

              return filter;
            });
            setBalanceDatas(processed);
            setPnl((parseFloat(balances.pop().Balance)-parseFloat(startBalance)).toFixed(2))
            setPnlDatas(processed);
            setWinningRateData([
              { name: 'win', value: win },
              { name: 'lose', value: lose },
            ]);
          };
        }
      } catch (error) {
        console.log(error)
      }
    };

    getVersions();
    getDatas();
  }, [version, startBalance])

  // 코인별 필터링
  const filteredBalanceDatas = useMemo(() => {
    if (selectedCoin === 'ALL') return balanceDatas;
    return balanceDatas.filter(d => d.symbol === selectedCoin + 'USDT');
  }, [balanceDatas, selectedCoin]);

  const filteredPnlDatas = useMemo(() => {
    if (selectedCoin === 'ALL') return pnlDatas;
    return pnlDatas.filter(d => d.symbol === selectedCoin + 'USDT');
  }, [pnlDatas, selectedCoin]);

  const filteredPnl = useMemo(() => {
    if (selectedCoin === 'ALL') return pnl;
    return filteredPnlDatas.reduce((sum, d) => sum + parseFloat(d.Profit), 0).toFixed(2);
  }, [selectedCoin, pnl, filteredPnlDatas]);

  const filteredNumTrade = useMemo(() => {
    if (selectedCoin === 'ALL') return numTrade;
    return filteredPnlDatas.length;
  }, [selectedCoin, numTrade, filteredPnlDatas]);

  const filteredWinRate = useMemo(() => {
    const data = selectedCoin === 'ALL' ? pnlDatas : filteredPnlDatas;
    let win = 0, lose = 0;
    data.forEach(d => {
      if (parseFloat(d.Profit) > 0) win += 1;
      else lose += 1;
    });
    return [{ name: 'win', value: win }, { name: 'lose', value: lose }];
  }, [selectedCoin, pnlDatas, filteredPnlDatas]);

  // 코인별 비교 데이터
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
    navigate('/');
  };

  const handleClickSidebarItem = (data) => {
    setVersion(data.version);
    setStartBalance(data.balance);
    setDate(data.date);
    setSelectedCoin('ALL');
  };

  const handleDeleteVersion = async (e, data) => {
    e.stopPropagation();
    if (!window.confirm(`"${data.version}" 모델을 삭제하시겠습니까?\n거래 기록도 함께 삭제됩니다.`)) return;
    try {
      const res = await axios.delete(`${process.env.REACT_APP_API_URL}/version`, {
        params: { id: data._id, version: data.version },
      });
      if (res.data.success) {
        setVersionDatas(prev => prev.filter(v => v._id !== data._id));
        if (version === data.version) {
          setVersion('');
          setBalanceDatas([]);
          setPnlDatas([]);
          setWinningRateData([]);
        }
      }
    } catch (err) {
      console.log(err);
      alert('삭제에 실패했습니다.');
    }
  };

  return(
    <div className={styles.background}>
      <div className={styles.sideBar}>
        {versionDatas.map((data) => {
          return(
            <div className={styles.sidebarItem} key={data._id} onClick={() => handleClickSidebarItem(data)}>
              <span className={styles.sidebarLabel}>{data.version}</span>
              <button
                className={styles.deleteBtn}
                onClick={(e) => handleDeleteVersion(e, data)}
                title="삭제"
              >
                ✕
              </button>
            </div>
          )
        })}
      </div>
      <div className={styles.contentContainer}>
        <div className={styles.headerContainer}>
          <div className={styles.titleContainer}>
            <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
            <div className={styles.modelName}>Model : {version}</div>
            <div className={styles.date}>Since: {date && formatTimestamp(date)}</div>
          </div>
          <button className={styles.button} onClick={handleClickButton}>Go Live</button>
        </div>

        {/* 코인 탭 */}
        {version && (
          <div className={styles.coinTabs}>
            {COINS.map(coin => (
              <button
                key={coin}
                className={`${styles.coinTab} ${selectedCoin === coin ? styles.coinTabActive : ''}`}
                onClick={() => setSelectedCoin(coin)}
              >
                {coin}
              </button>
            ))}
          </div>
        )}

        <div className={styles.row}>
          <div className={`${styles.assetContent} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.name}>{selectedCoin === 'ALL' ? 'Asset Value' : `${selectedCoin} Trades`}</div>
            </div>
            <div className={styles.graph}>
              <LineGraph datas={filteredBalanceDatas} />
            </div>
          </div>
          <div className={`${styles.rorContent} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.statistics}>Winning Rate</div>
            </div>
            <div className={styles.pieGraph}>
              <PieGraph datas={filteredWinRate} />
            </div>
            <div className={styles.floor}>
              <div className={styles.statistics}>Total Trade : {filteredNumTrade}</div>
            </div>
            <div className={styles.floor}>
              <div className={styles.statistics}>Total ROR :</div>
              <div className={filteredPnl > 0 ? styles.plus : styles.minus}>
                {startBalance ? (filteredPnl / startBalance * 100).toFixed(2) : '0.00'} %
              </div>
            </div>
          </div>
        </div>
        <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.name}>{selectedCoin === 'ALL' ? 'Profit and Loss ($)' : `${selectedCoin} P&L ($)`}</div>
            <div className={filteredPnl > 0 ? styles.plus : styles.minus}><span className={styles.label}>Total :</span>{filteredPnl} $</div>
          </div>
          <div className={styles.graph}>
            <BarGraph datas={filteredPnlDatas} />
          </div>
        </div>

        {/* 코인별 비교 차트 */}
        {selectedCoin === 'ALL' && coinSummary.length > 0 && (
          <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.name}>Coin Performance</div>
            </div>
            <div className={styles.graph}>
              <CoinComparisonChart datas={coinSummary} onCoinClick={(coin) => setSelectedCoin(coin)} />
            </div>
          </div>
        )}

        {/* Analytics Report */}
        {filteredPnlDatas.length > 0 && (
          <div className={`${styles.analyticsSection} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.name}>
                {selectedCoin === 'ALL' ? 'Analytics Report' : `${selectedCoin} Analytics`}
              </div>
            </div>
            <AnalyticsReport
              trades={filteredPnlDatas}
              selectedCoin={selectedCoin}
              startBalance={startBalance}
            />
          </div>
        )}
      </div>
    </div>
  )
};

export default History;
