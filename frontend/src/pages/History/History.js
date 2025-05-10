import { useEffect, useState } from 'react'
import styles from './History.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import PieGraph from '../../components/Graph/PieGraph';
import { useNavigate } from 'react-router-dom';

const History = () => {
  const [versionDatas, setVersionDatas] = useState([]);
  const [startBalance, setStartBalance] = useState('');
  const [date, setDate] = useState('');
  const [pnl, setPnl] = useState(0);
  const [numTrade, setNumTrade] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [winningRateData, setWinningRateData] = useState([]);

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
              filter['Profit'] = parseFloat(data.profit).toFixed(2);
              if (data.ror > 0) {
                win += 1;
              } else {
                lose += 1;
              };

              return filter;
            });
            // setPnl(totalPnl.toFixed(2));
            setBalanceDatas(balances);
            setPnl((parseFloat(balances.pop().Balance)-parseFloat(startBalance)).toFixed(2))
            setPnlDatas(processed);
            setWinningRateData([
              {
                name: 'win',
                value: win,
              },
              {
                name: 'lose',
                value: lose,
              }
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

  const handleClickButton = () => {
    navigate('/');
  };

  const handleClickSidebarItem = (data) => {
    setVersion(data.version);
    setStartBalance(data.balance);
    setDate(data.date);
  };

  return(
    <div className={styles.background}>
      <div className={styles.sideBar}>
        {versionDatas.map((data) => {
          return(
            <div className={styles.sidebarItem} key={data._id} onClick={() => handleClickSidebarItem(data)}>
              {data.version}
            </div>
          )
        })}
      </div>
      <div className={styles.contentContainer}>
        <div className={styles.headerContainer}>
          <div className={styles.titleContainer}>
            <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
            <div className={styles.modelName}>Current Model : {version}</div>
            <div className={styles.date}>Since: {date && formatTimestamp(date)}</div>
          </div>
          <button className={styles.button} onClick={handleClickButton}>Go Live</button>
        </div>
        <div className={styles.row}>
          <div className={`${styles.assetContent} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.name}>Asset Value</div>
            </div>
            <div className={styles.graph}>
              <LineGraph datas={balanceDatas} />
            </div>
          </div>
          <div className={`${styles.rorContent} ${styles.glow_box} ${styles.gradient_border}`}>
            <div className={styles.header}>
              <div className={styles.statistics}>Winning Rate</div>
            </div>
            <div className={styles.pieGraph}>
              <PieGraph datas={winningRateData} />
            </div>
            <div className={styles.floor}>
              <div className={styles.statistics}>Total Trade : {numTrade}</div>
            </div>
            <div className={styles.floor}>
              <div className={styles.statistics}>Total ROR :</div>
              <div className={pnl > 0 ? styles.plus : styles.minus}>{(pnl && pnl/startBalance*100).toFixed(2)} %</div>
            </div>
          </div>
        </div>
        <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.name}>Profit and Loss ($)</div>
            <div className={pnl > 0 ? styles.plus : styles.minus}><span className={styles.label}>Total :</span>{pnl} $</div>
          </div>
          <div className={styles.graph}>
            <BarGraph datas={pnlDatas} />
          </div>
        </div>
      </div>
    </div>
  )
};

export default History;
