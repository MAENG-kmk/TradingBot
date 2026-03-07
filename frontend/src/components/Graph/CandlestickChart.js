import { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, ColorType, createSeriesMarkers } from 'lightweight-charts';

const CandlestickChart = ({ candles, trades }) => {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartContainerRef.current || !candles || candles.length === 0) return;

    // 이전 차트 제거
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#a8a8a8',
        fontFamily: 'Orbitron, sans-serif',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: 'rgba(255,255,255,0.1)',
      },
      timeScale: {
        borderColor: 'rgba(255,255,255,0.1)',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#4CAF50',
      downColor: '#F44336',
      borderDownColor: '#F44336',
      borderUpColor: '#4CAF50',
      wickDownColor: '#F44336',
      wickUpColor: '#4CAF50',
    });

    candleSeries.setData(candles);

    // 거래 마커 추가
    if (trades && trades.length > 0) {
      const markers = [];

      trades.forEach((trade) => {
        const enterTs = trade.enterTimestamp;
        const closeTs = trade.closeTimestamp;
        const isProfit = parseFloat(trade.Profit) > 0;
        const isLong = trade.side === 'long';

        if (enterTs) {
          markers.push({
            time: enterTs,
            position: isLong ? 'belowBar' : 'aboveBar',
            color: '#00bcd4',
            shape: isLong ? 'arrowUp' : 'arrowDown',
            text: `${isLong ? 'L' : 'S'} Entry`,
          });
        }

        if (closeTs) {
          markers.push({
            time: closeTs,
            position: isProfit ? 'aboveBar' : 'belowBar',
            color: isProfit ? '#4CAF50' : '#F44336',
            shape: 'circle',
            text: `${trade.Profit}$`,
          });
        }
      });

      markers.sort((a, b) => a.time - b.time);
      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    // 리사이즈 대응
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [candles, trades]);

  return <div ref={chartContainerRef} style={{ width: '100%', height: '100%' }} />;
};

export default CandlestickChart;
