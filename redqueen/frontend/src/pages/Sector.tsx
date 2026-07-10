import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Table, Input, Button, message, Spin, Card } from 'antd';
import { StarFilled, StarOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import * as echarts from 'echarts';
import { getSectorList, getLatestTradingDay, getSectorStocks, updateSectorStocks, getStockKLineData, getFavoriteList, upsertFavorite } from '../api/api';
import type { ConceptPlateData, SectorStockData } from '../api/api';

interface KLineData {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  amount: number;
  change_rate: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  ma120?: number;
}

const Sector: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [sectors, setSectors] = useState<ConceptPlateData[]>([]);
  const [searchName, setSearchName] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [sortConfig, setSortConfig] = useState<{ key: keyof ConceptPlateData; direction: 'ascend' | 'descend' } | null>(null);
  const [selectedSector, setSelectedSector] = useState<ConceptPlateData | null>(null);
  const [stocks, setStocks] = useState<SectorStockData[]>([]);
  const [stockLoading, setStockLoading] = useState<boolean>(false);
  const [stockSortConfig, setStockSortConfig] = useState<{ key: string; direction: 'ascend' | 'descend' } | null>(null);
  const [updateLoading, setUpdateLoading] = useState<boolean>(false);
  const [latestFetchTime, setLatestFetchTime] = useState<string | null>(null);

  const [selectedStock, setSelectedStock] = useState('');
  const [kLineLoading, setKLineLoading] = useState(false);
  const [kLineData, setKLineData] = useState<KLineData[]>([]);
  const [showKLineChart, setShowKLineChart] = useState(false);
  const [favStockCodes, setFavStockCodes] = useState<Set<string>>(new Set());
  const kLineChartRef = useRef<HTMLDivElement>(null);
  const kLineChartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    loadLatestTradingDay();
    loadFavorites();
  }, []);

  const loadFavorites = async () => {
    try {
      const list = await getFavoriteList();
      const codes = new Set(list.filter((item: any) => item.status === 1).map((item: any) => item.stock_code));
      setFavStockCodes(codes);
    } catch (e: any) {
      console.error('加载收藏列表失败:', e);
    }
  };

  const toggleFavorite = async (stockCode: string) => {
    const currentlyFav = favStockCodes.has(stockCode);
    const nextStatus = currentlyFav ? 0 : 1;
    const payload: { price_date?: string; status: number; tag?: string } = { status: nextStatus };
    if (nextStatus === 1) {
      payload.price_date = selectedDate;
    }
    try {
      await upsertFavorite(stockCode, payload);
      const next = new Set(favStockCodes);
      if (nextStatus === 1) {
        next.add(stockCode);
        message.success(`已收藏 ${stockCode}`);
      } else {
        next.delete(stockCode);
        message.success(`已取消收藏 ${stockCode}`);
      }
      setFavStockCodes(next);
    } catch (e: any) {
      console.error('收藏操作失败:', e);
      message.error('收藏操作失败');
    }
  };

  const loadLatestTradingDay = async () => {
    try {
      const result = await getLatestTradingDay();
      const latestDate = result.date;
      setSelectedDate(latestDate);
      fetchSectorData(latestDate);
    } catch (error) {
      message.error('获取最新交易日失败');
      fetchSectorData(selectedDate);
    }
  };

  const fetchSectorData = async (date: string) => {
    setLoading(true);
    try {
      const data = await getSectorList(date);
      setSectors(data);
      if (data.length > 0 && !selectedSector) {
        setSelectedSector(data[0]);
      }
    } catch (error) {
      console.error('获取概念板块数据失败:', error);
      message.error('获取概念板块数据失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchStockData = async (conceptId: string, conceptName: string) => {
    setStockLoading(true);
    try {
      const result = await getSectorStocks(conceptId, conceptName, selectedDate);
      setStocks(result.data);
      setLatestFetchTime(result.latest_fetch_time);
      if (!result.has_local_data) {
        message.info('无本地数据');
      }
    } catch (error) {
      console.error('获取概念个股数据失败:', error);
      message.error('获取概念个股数据失败');
    } finally {
      setStockLoading(false);
    }
  };

  const handleUpdateStocks = async () => {
    if (!selectedSector) return;
    
    setUpdateLoading(true);
    try {
      const result = await updateSectorStocks(selectedSector.concept_id, selectedSector.concept_name);
      if (result.success) {
        message.success(`${result.message}，共${result.updated_count}只股票`);
        await fetchStockData(selectedSector.concept_id, selectedSector.concept_name);
      } else {
        message.error('更新失败');
      }
    } catch (error) {
      console.error('更新概念个股数据失败:', error);
      message.error('更新概念个股数据失败');
    } finally {
      setUpdateLoading(false);
    }
  };

  const fetchKLineData = useCallback(async (stockCode: string) => {
    if (!stockCode || !selectedDate) {
      return;
    }

    setKLineLoading(true);
    setKLineData([]);

    if (kLineChartInstance.current) {
      kLineChartInstance.current.clear();
    }

    try {
      const kLineResult = await getStockKLineData(stockCode, 9999, selectedDate);

      if (Array.isArray(kLineResult) && kLineResult.length > 0) {
        setKLineData(kLineResult);
      } else {
        const fallback = await getStockKLineData(stockCode, 9999, '');
        if (Array.isArray(fallback) && fallback.length > 0) {
          setKLineData(fallback);
        }
      }
    } catch (error) {
      console.error('获取 K 线数据失败:', error);
      message.error('获取 K 线数据失败');
    } finally {
      setKLineLoading(false);
    }
  }, [selectedDate]);

  const renderKLineChart = useCallback((chartData: KLineData[]) => {
    if (!kLineChartRef.current || !Array.isArray(chartData) || chartData.length === 0) {
      return;
    }

    const container = kLineChartRef.current;
    const rect = container.getBoundingClientRect();

    if (!kLineChartInstance.current) {
      kLineChartInstance.current = echarts.init(container);
    }

    if (rect.height < 350) {
      container.style.minHeight = '350px';
    }

    kLineChartInstance.current.resize();

    const convertedData = chartData.map(item => [
      item.date,
      parseFloat(item.open as any) || 0,
      parseFloat(item.close as any) || 0,
      parseFloat(item.low as any) || 0,
      parseFloat(item.high as any) || 0
    ]);

    const volumeData = chartData.map(item => [
      item.date,
      item.volume ? parseFloat(item.volume as any) : 0
    ]);

    const ma5Data = chartData.map(item => [
      item.date,
      item.ma5 !== null ? parseFloat(item.ma5 as any) : null
    ]);
    const ma10Data = chartData.map(item => [
      item.date,
      item.ma10 !== null ? parseFloat(item.ma10 as any) : null
    ]);
    const ma20Data = chartData.map(item => [
      item.date,
      item.ma20 !== null ? parseFloat(item.ma20 as any) : null
    ]);
    const ma60Data = chartData.map(item => [
      item.date,
      item.ma60 !== null ? parseFloat(item.ma60 as any) : null
    ]);

    const computeRollingHigh = (items: KLineData[], period: number) => {
      const highs: (number | null)[] = [];
      for (let i = 0; i < items.length; i++) {
        const start = Math.max(0, i - period + 1);
        let h = -Infinity;
        let valid = false;
        for (let j = start; j <= i; j++) {
          const hj = parseFloat(items[j].high as any);
          if (!isNaN(hj) && hj > h) {
            h = hj;
            valid = true;
          }
        }
        highs.push(valid ? h : null);
      }
      return highs;
    };

    const h60Data = computeRollingHigh(chartData, 60);

    const totalDays = chartData.length;
    const defaultViewDays = 90;
    const startPercent = totalDays > defaultViewDays ? ((totalDays - defaultViewDays) / totalDays) * 100 : 0;
    const endPercent = 100;

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          crossStyle: {
            color: '#999'
          }
        },
        formatter: function(params: any) {
          if (!params || !params.length) return '';

          let klineData: any = null;
          let dataIndex: number = -1;

          for (const item of params) {
            if (item.seriesName === 'K 线') {
              klineData = item.data;
              dataIndex = item.dataIndex;
              break;
            }
          }

          if (!klineData || dataIndex === -1) return '';

          const stockData = chartData[dataIndex];
          const volume = stockData.volume ? stockData.volume.toFixed(2) : '0.00';
          const amount = stockData.amount ? stockData.amount.toFixed(2) : '0.00';
          const ma5 = stockData.ma5 ? stockData.ma5.toFixed(2) : '-';
          const ma10 = stockData.ma10 ? stockData.ma10.toFixed(2) : '-';
          const ma20 = stockData.ma20 ? stockData.ma20.toFixed(2) : '-';
          const ma60 = stockData.ma60 ? stockData.ma60.toFixed(2) : '-';
          const h60 = h60Data[dataIndex] !== null ? h60Data[dataIndex]?.toFixed(2) : '-';

          const open = klineData[1] || 0;
          const close = klineData[2] || 0;
          const low = klineData[3] || 0;
          const high = klineData[4] || 0;
          const changeRateValue = typeof stockData.change_rate === 'number' ? stockData.change_rate : parseFloat(stockData.change_rate) || 0;
          const changeRateColor = changeRateValue >= 0 ? '#ef232a' : '#11c26d';

          return `日期: ${stockData.date}<br/>
                 开盘: ${open.toFixed(2)}<br/>
                 收盘: ${close.toFixed(2)}<br/>
                 最低: ${low.toFixed(2)}<br/>
                 最高: ${high.toFixed(2)}<br/>
                 涨跌幅: <span style="color: ${changeRateColor}">${changeRateValue >= 0 ? '+' : ''}${changeRateValue.toFixed(2)}%</span><br/>
                 MA5: ${ma5}<br/>
                 MA10: ${ma10}<br/>
                 MA20: ${ma20}<br/>
                 MA60: ${ma60}<br/>
                 H60: ${h60}<br/>
                 成交量: ${volume}<br/>
                 成交额: ${amount}`;
        }
      },
      legend: {
        data: [
          { name: 'K 线', itemStyle: { color: '#ef232a' } },
          { name: 'MA5', itemStyle: { color: '#4874CB' } },
          { name: 'MA10', itemStyle: { color: '#B68D01' } },
          { name: 'MA20', itemStyle: { color: '#BD5AFF' } },
          { name: 'MA60', itemStyle: { color: '#689EFF' } },
          { name: 'H60', itemStyle: { color: '#ef232a' } },
          { name: '成交量', itemStyle: { color: '#ef232a' } }
        ],
        top: 0,
        left: 0,
        align: 'left'
      },
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: [0, 1],
          start: startPercent,
          end: endPercent,
          zoomLock: false
        },
        {
          xAxisIndex: [0, 1],
          start: startPercent,
          end: endPercent,
          height: 20,
          bottom: 5,
          zoomLock: false,
          showDetail: true
        }
      ],
      grid: [
        {
          left: 80,
          right: 40,
          top: 45,
          bottom: '30%',
          containLabel: false
        },
        {
          left: 80,
          right: 40,
          top: '70%',
          bottom: 30,
          containLabel: false
        }
      ],
      xAxis: [
        {
          type: 'category',
          boundaryGap: true,
          data: chartData.map(item => item.date),
          axisLine: {
            show: true,
            lineStyle: {
              color: '#ccc'
            }
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            show: true
          },
          splitLine: {
            show: false
          }
        },
        {
          type: 'category',
          boundaryGap: true,
          data: chartData.map(item => item.date),
          gridIndex: 1,
          axisLine: {
            show: true,
            lineStyle: {
              color: '#ccc'
            }
          },
          axisTick: {
            alignWithLabel: true
          },
          axisLabel: {
            show: false
          },
          splitLine: {
            show: false
          }
        }
      ],
      yAxis: [
        {
          type: 'value',
          scale: true,
          splitNumber: 4,
          axisLine: {
            show: true,
            lineStyle: {
              color: '#ccc'
            }
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            color: '#333',
            fontSize: 13,
            formatter: function(value: any) {
              return value.toFixed(2);
            }
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: '#eee',
              type: 'dashed'
            }
          }
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLine: {
            show: false
          },
          axisTick: {
            show: false
          },
          axisLabel: {
            show: false
          },
          splitLine: {
            show: true,
            lineStyle: {
              color: '#eee',
              type: 'dashed'
            }
          }
        }
      ],
      axisPointer: {
        link: [{ xAxisIndex: 'all' }]
      },
      series: [
        {
          name: 'K 线',
          type: 'candlestick',
          data: convertedData.map(item => [item[1], item[2], item[3], item[4]]),
          itemStyle: {
            color: '#ef232a',
            color0: '#11c26d',
            borderColor: '#ef232a',
            borderColor0: '#11c26d'
          }
        },
        {
          name: 'MA5',
          type: 'line',
          data: ma5Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: '#4874CB'
          },
          symbol: 'none'
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: '#B68D01'
          },
          symbol: 'none'
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: '#BD5AFF'
          },
          symbol: 'none'
        },
        {
          name: 'MA60',
          type: 'line',
          data: ma60Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1.5,
            color: '#689EFF'
          },
          symbol: 'none'
        },
        {
          name: 'H60',
          type: 'line',
          data: h60Data,
          smooth: false,
          lineStyle: {
            width: 1,
            color: '#ef232a',
            type: 'dashed'
          },
          symbol: 'none'
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeData.map(item => item[1]),
          itemStyle: {
            color: function(params: any) {
              const index = params.dataIndex;
              const klineData = convertedData[index];
              return klineData[2] >= klineData[1] ? '#ef232a' : '#11c26d';
            }
          }
        }
      ]
    };

    kLineChartInstance.current.setOption(option, true);
  }, []);

  useEffect(() => {
    if (kLineData.length > 0 && kLineChartRef.current) {
      renderKLineChart(kLineData);
    }
  }, [kLineData, renderKLineChart]);

  useEffect(() => {
    if (showKLineChart && kLineData.length > 0 && kLineChartRef.current) {
      renderKLineChart(kLineData);
    }
  }, [showKLineChart, kLineData, kLineChartRef, renderKLineChart]);

  useEffect(() => {
    const handleResize = () => {
      if (kLineChartInstance.current) {
        kLineChartInstance.current.resize();
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleStockClick = (record: SectorStockData) => {
    if (record && record.stock_code) {
      setSelectedStock(record.stock_code);
      setShowKLineChart(true);
      fetchKLineData(record.stock_code);
    }
  };

  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      fetchSectorData(newDate);
    }
  };

  const handleSort = (key: keyof ConceptPlateData) => {
    let direction: 'ascend' | 'descend' = 'ascend';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascend') {
      direction = 'descend';
    }
    setSortConfig({ key, direction });
  };

  const getColorStyle = (value: number | null) => {
    if (value === null) return {};
    if (value > 5) {
      return { backgroundColor: '#fde2e2', color: '#9d0208', fontWeight: 'bold' };
    } else if (value > 3) {
      return { backgroundColor: '#fee2e2', color: '#dc2626' };
    } else if (value > 1) {
      return { backgroundColor: '#fef2f2', color: '#ef4444' };
    } else if (value > 0) {
      return { backgroundColor: '#fff1f0', color: '#f87171' };
    } else if (value < -5) {
      return { backgroundColor: '#d1fae5', color: '#065f46', fontWeight: 'bold' };
    } else if (value < -3) {
      return { backgroundColor: '#d1fae5', color: '#059669' };
    } else if (value < -1) {
      return { backgroundColor: '#ecfdf5', color: '#10b981' };
    } else if (value < 0) {
      return { backgroundColor: '#f0fdf4', color: '#34d399' };
    }
    return {};
  };

  const getChangeColor = (value: number) => {
    return value >= 0 ? '#ef232a' : '#11c26d';
  };

  const filteredSectors = searchName
    ? sectors.filter(item =>
        item.concept_name.toLowerCase().includes(searchName.toLowerCase())
      )
    : sectors;

  const sortedSectors = [...filteredSectors].sort((a, b) => {
    if (!sortConfig) {
      const aChg = a.avg_change_ratio ?? 0;
      const bChg = b.avg_change_ratio ?? 0;
      return bChg - aChg;
    }
    const key = sortConfig.key;
    const aValue = a[key];
    const bValue = b[key];
    if (typeof aValue === 'number' && typeof bValue === 'number') {
      return sortConfig.direction === 'ascend' ? aValue - bValue : bValue - aValue;
    }
    if (typeof aValue === 'string' && typeof bValue === 'string') {
      return sortConfig.direction === 'ascend'
        ? aValue.localeCompare(bValue)
        : bValue.localeCompare(aValue);
    }
    return 0;
  });

  const handleStockSort = (key: string) => {
    setStockSortConfig(prev => {
      if (!prev) {
        return { key, direction: 'descend' };
      }
      if (prev.key === key) {
        return { key, direction: prev.direction === 'ascend' ? 'descend' : 'ascend' };
      }
      return { key, direction: 'descend' };
    });
  };

  const sortedStocks = [...stocks].sort((a, b) => {
    if (!stockSortConfig) {
      const aDays = a.growth_streak_days ?? 0;
      const bDays = b.growth_streak_days ?? 0;
      return bDays - aDays;
    }
    const key = stockSortConfig.key;
    const aValue = (a as any)[key] ?? 0;
    const bValue = (b as any)[key] ?? 0;
    if (typeof aValue === 'number' && typeof bValue === 'number') {
      return stockSortConfig.direction === 'ascend' ? aValue - bValue : bValue - aValue;
    }
    return 0;
  });

  const sectorColumns: ColumnsType<ConceptPlateData> = [
    {
      title: 'Sector',
      dataIndex: 'concept_name',
      key: 'concept_name',
      width: 110,
      ellipsis: true,
      sorter: (a, b) => a.concept_name.localeCompare(b.concept_name),
      sortOrder: sortConfig && sortConfig.key === 'concept_name' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('concept_name')
      })
    },
    {
      title: 'Count',
      dataIndex: 'stock_count',
      key: 'stock_count',
      width: 60,
      align: 'right',
      sorter: (a, b) => (a.stock_count || 0) - (b.stock_count || 0),
      sortOrder: sortConfig && sortConfig.key === 'stock_count' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('stock_count')
      }),
      render: (text: number) => (
        <span>{typeof text === 'number' ? text : 0}</span>
      )
    },
    {
      title: 'VOL',
      key: 'avg_volume',
      width: 80,
      align: 'right',
      sorter: (a, b) => {
        const aVol = a.total_volume && a.stock_count ? a.total_volume / a.stock_count : 0;
        const bVol = b.total_volume && b.stock_count ? b.total_volume / b.stock_count : 0;
        return aVol - bVol;
      },
      sortOrder: sortConfig && sortConfig.key === 'avg_volume' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('avg_volume')
      }),
      render: (_: any, record: ConceptPlateData) => {
        const vol = record.total_volume;
        const count = record.stock_count;
        if (!vol || !count) {
          return <span>-</span>;
        }
        const avgVol = vol / count ;
        return <span>{avgVol.toFixed(0)}</span>;
      }
    },
    {
      title: 'Chg%',
      dataIndex: 'avg_change_ratio',
      key: 'avg_change_ratio',
      width: 75,
      align: 'right',
      sorter: (a, b) => (a.avg_change_ratio || 0) - (b.avg_change_ratio || 0),
      sortOrder: sortConfig && sortConfig.key === 'avg_change_ratio' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('avg_change_ratio')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#11c26d' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Chg-1%',
      dataIndex: 'chg_1',
      key: 'chg_1',
      width: 70,
      align: 'right',
      sorter: (a, b) => (a.chg_1 ?? 0) - (b.chg_1 ?? 0),
      sortOrder: sortConfig && sortConfig.key === 'chg_1' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('chg_1')
      }),
      render: (text: number | null) => (
        <span style={getColorStyle(text)}>
          {text !== null ? text.toFixed(2) : '-'}
        </span>
      )
    },
    {
      title: 'Chg-2%',
      dataIndex: 'chg_2',
      key: 'chg_2',
      width: 70,
      align: 'right',
      sorter: (a, b) => (a.chg_2 ?? 0) - (b.chg_2 ?? 0),
      sortOrder: sortConfig && sortConfig.key === 'chg_2' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('chg_2')
      }),
      render: (text: number | null) => (
        <span style={getColorStyle(text)}>
          {text !== null ? text.toFixed(2) : '-'}
        </span>
      )
    },
    {
      title: 'Chg-3%',
      dataIndex: 'chg_3',
      key: 'chg_3',
      width: 70,
      align: 'right',
      sorter: (a, b) => (a.chg_3 ?? 0) - (b.chg_3 ?? 0),
      sortOrder: sortConfig && sortConfig.key === 'chg_3' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('chg_3')
      }),
      render: (text: number | null) => (
        <span style={getColorStyle(text)}>
          {text !== null ? text.toFixed(2) : '-'}
        </span>
      )
    },
    {
      title: 'Chg-4%',
      dataIndex: 'chg_4',
      key: 'chg_4',
      width: 70,
      align: 'right',
      sorter: (a, b) => (a.chg_4 ?? 0) - (b.chg_4 ?? 0),
      sortOrder: sortConfig && sortConfig.key === 'chg_4' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('chg_4')
      }),
      render: (text: number | null) => (
        <span style={getColorStyle(text)}>
          {text !== null ? text.toFixed(2) : '-'}
        </span>
      )
    },
    {
      title: 'Chg-5%',
      dataIndex: 'chg_5',
      key: 'chg_5',
      width: 70,
      align: 'right',
      sorter: (a, b) => (a.chg_5 ?? 0) - (b.chg_5 ?? 0),
      sortOrder: sortConfig && sortConfig.key === 'chg_5' ? sortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleSort('chg_5')
      }),
      render: (text: number | null) => (
        <span style={getColorStyle(text)}>
          {text !== null ? text.toFixed(2) : '-'}
        </span>
      )
    }
  ];

  const stockColumns: ColumnsType<SectorStockData> = [
    {
      title: 'Fav',
      key: 'favorite',
      width: 40,
      align: 'center',
      render: (_: any, record: SectorStockData) => {
        const isFav = favStockCodes.has(record.stock_code);
        return (
          <Button
            type="text"
            size="small"
            style={{ padding: 0 }}
            onClick={(e) => {
              e.stopPropagation();
              toggleFavorite(record.stock_code);
            }}
            icon={isFav ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined style={{ color: '#bfbfbf' }} />}
          />
        );
      }
    },
    {
      title: 'Code',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 70,
    },
    {
      title: 'Name',
      dataIndex: 'stock_name',
      key: 'stock_name',
      width: 90,
      ellipsis: true,
    },
    {
      title: 'Close',
      dataIndex: 'close',
      key: 'close',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.close || 0) - (b.close || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'close' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('close')
      }),
      render: (text: number) => (
        <span style={{ fontSize: '12px' }}>{typeof text === 'number' ? text.toFixed(2) : '0.00'}</span>
      )
    },
    {
      title: 'Chg%',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 75,
      align: 'right',
      sorter: (a, b) => (a.change_pct || 0) - (b.change_pct || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'change_pct' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('change_pct')
      }),
      render: (text: number) => (
        <span style={{ color: getChangeColor(text), fontSize: '12px' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Days',
      dataIndex: 'growth_streak_days',
      key: 'growth_streak_days',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.growth_streak_days || 0) - (b.growth_streak_days || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'growth_streak_days' ? stockSortConfig.direction : 'descend',
      onHeaderCell: () => ({
        onClick: () => handleStockSort('growth_streak_days')
      }),
      render: (text: number | null) => {
        const value = typeof text === 'number' ? text : parseFloat(text || '0') || 0;
        return <span style={{ fontSize: '12px' }}>{Math.floor(value)}</span>;
      },
    },
    {
      title: 'Days%',
      dataIndex: 'growth_streak_pct',
      key: 'growth_streak_pct',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.growth_streak_pct || 0) - (b.growth_streak_pct || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'growth_streak_pct' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('growth_streak_pct')
      }),
      render: (text: number | null) => {
        const value = typeof text === 'number' ? text : parseFloat(text || '0') || 0;
        return (
          <span style={{ color: value >= 0 ? '#ef232a' : '#11c26d', fontSize: '12px' }}>
            {value >= 0 ? '+' : ''}{value.toFixed(1)}
          </span>
        );
      },
    },
    {
      title: 'per%',
      key: 'chg_days_pct',
      width: 80,
      align: 'right',
      sorter: (a, b) => {
        const aDays = a.growth_streak_days || 0;
        const bDays = b.growth_streak_days || 0;
        const aVal = aDays > 0 ? (a.growth_streak_pct || 0) / aDays : 0;
        const bVal = bDays > 0 ? (b.growth_streak_pct || 0) / bDays : 0;
        return aVal - bVal;
      },
      sortOrder: stockSortConfig && stockSortConfig.key === 'chg_days_pct' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('chg_days_pct')
      }),
      render: (_: any, record: SectorStockData) => {
        const days = record.growth_streak_days || 0;
        if (days === 0) {
          return <span style={{ fontSize: '12px' }}>-</span>;
        }
        const streakPct = typeof record.growth_streak_pct === 'number' ? record.growth_streak_pct : parseFloat(record.growth_streak_pct || '0') || 0;
        const value = streakPct / days;
        return (
          <span style={{ color: value >= 0 ? '#ef232a' : '#11c26d', fontSize: '12px' }}>
            {value >= 0 ? '+' : ''}{value.toFixed(1)}
          </span>
        );
      },
    },
    {
      title: 'VOL%',
      dataIndex: 'volume_pct',
      key: 'volume_pct',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.volume_pct || 0) - (b.volume_pct || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'volume_pct' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('volume_pct')
      }),
      render: (text: number | null) => {
        const value = typeof text === 'number' ? text : parseFloat(text || '0') || 0;
        const color = value >= 0 ? '#ef232a' : '#11c26d';
        return (
          <span style={{ color: color, fontSize: '12px' }}>
            {value >= 0 ? '+' : ''}{value.toFixed(1)}
          </span>
        );
      },
    },
    {
      title: 'Dh20',
      dataIndex: 'high_20d_last',
      key: 'high_20d_last',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.high_20d_last || 0) - (b.high_20d_last || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'high_20d_last' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('high_20d_last')
      }),
      render: (text: number | null) => {
        const value = typeof text === 'number' ? text : parseInt(text || '0') || 0;
        return <span style={{ fontSize: '12px' }}>{value > 0 ? value : '0'}</span>;
      },
    },
    {
      title: 'Dh120',
      dataIndex: 'high_120d_last',
      key: 'high_120d_last',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.high_120d_last || 0) - (b.high_120d_last || 0),
      sortOrder: stockSortConfig && stockSortConfig.key === 'high_120d_last' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('high_120d_last')
      }),
      render: (text: number | null) => {
        const value = typeof text === 'number' ? text : parseInt(text || '0') || 0;
        return <span style={{ fontSize: '12px' }}>{value > 0 ? value : '0'}</span>;
      },
    },
    {
      title: 'C/H%',
      key: 'close_h20_pct',
      width: 70,
      align: 'right',
      sorter: (a, b) => {
        const aH20 = typeof a.high_20d === 'number' ? a.high_20d : parseFloat(a.high_20d || '0') || 0;
        const bH20 = typeof b.high_20d === 'number' ? b.high_20d : parseFloat(b.high_20d || '0') || 0;
        const aClose = typeof a.close === 'number' ? a.close : parseFloat(a.close || '0') || 0;
        const bClose = typeof b.close === 'number' ? b.close : parseFloat(b.close || '0') || 0;
        const aVal = aH20 > 0 ? ((aClose / aH20) - 1) * 100 : 0;
        const bVal = bH20 > 0 ? ((bClose / bH20) - 1) * 100 : 0;
        return aVal - bVal;
      },
      sortOrder: stockSortConfig && stockSortConfig.key === 'close_h20_pct' ? stockSortConfig.direction : false,
      onHeaderCell: () => ({
        onClick: () => handleStockSort('close_h20_pct')
      }),
      render: (_: any, record: SectorStockData) => {
        const h20 = typeof record.high_20d === 'number' ? record.high_20d : parseFloat(record.high_20d || '0') || 0;
        const close = typeof record.close === 'number' ? record.close : parseFloat(record.close || '0') || 0;
        if (h20 <= 0) {
          return <span style={{ fontSize: '12px' }}>-</span>;
        }
        const value = ((close / h20) - 1) * 100;
        return (
          <span style={{ color: value >= 0 ? '#ef232a' : '#11c26d', fontSize: '12px' }}>
            {value >= 0 ? '+' : ''}{value.toFixed(1)}
          </span>
        );
      },
    },
  ];

  const formatFetchTime = (time: string | null) => {
    if (!time) return '无数据';
    const date = new Date(time);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: '800px' }}>
      <div style={{ width: '100%', flex: 1, display: 'flex', gap: 12, overflowX: 'hidden' }}>
        <div style={{ flex: 5.5, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column', minHeight: '900px' }} title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <span style={{ fontWeight: 'bold', fontSize: '14px' }}>概念板块</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => handleDateChange(e.target.value)}
                  style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '28px', fontSize: '12px' }}
                />
                <Input
                  placeholder="Search by Sector"
                  style={{ width: 160 }}
                  value={searchName}
                  onChange={(e) => setSearchName(e.target.value)}
                  allowClear
                  size="small"
                />
              </div>
            </div>
          }>
            <div style={{ marginTop: -12, marginBottom: 12 , overflowX: 'auto' }}>  {/*  与上方间距 */}
              <div style={{ minWidth: 800 }}>
                <Table
                  columns={sectorColumns}
                  dataSource={sortedSectors}
                  rowKey="concept_name"
                  pagination={false}
                  size="small"
                  loading={loading}
                  scroll={{ y: 'calc(100vh - 220px)' }}
                  rowClassName={(record: any) =>
                    record && record.concept_id === selectedSector?.concept_id ? 'ant-table-row-hover-selected' : ''
                  }
                  onRow={(record) => ({
                    onClick: () => {
                      setSelectedSector(record);
                      fetchStockData(record.concept_id, record.concept_name);
                    }
                  })}
                />
              </div>
            </div>
          </Card>
        </div>
        
        <div style={{ flex: 4.5, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, minWidth: 900, padding: 0, display: 'flex', flexDirection: 'column', minHeight: '900px' }} title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <div>
                <span>{selectedSector?.concept_name || '请选择概念'}</span>
                {latestFetchTime && (
                  <span style={{ marginLeft: '16px', fontSize: '12px', color: '#999' }}>
                    更新时间: {formatFetchTime(latestFetchTime)}
                  </span>
                )}
              </div>
              <Button
                type="primary"
                size="small"
                loading={updateLoading}
                onClick={handleUpdateStocks}
                disabled={!selectedSector}
              >
                更新数据
              </Button>
            </div>
          }>
            {showKLineChart && (
              <div style={{ marginTop: -12, marginBottom: 12 , borderBottom: '1px solid #f0f0f0', flexShrink: 0 }}>
                <div>
                  <div style={{
                    background: '#f5f5f5',
                    padding: '6px 12px',
                    borderRadius: 8,
                    marginBottom: 2,
                    fontSize: 12,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}>
                    <div>
                      <span style={{ fontWeight: 'bold' }}>
                        {selectedStock} - {stocks.find(s => s.stock_code === selectedStock)?.stock_name || ''}
                      </span>
                      <span style={{ marginLeft: 16, color: '#666', fontWeight: 'bold' }}>
                        数据日期 {selectedDate}
                      </span>
                      <span style={{ marginLeft: 16 }}>
                        <a
                          href={`https://q.stock.sohu.com/cn/${selectedStock}/index.shtml`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ textDecoration: 'none', color: '#1890ff' }}
                        >
                          SOHU
                        </a>
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        if (kLineChartInstance.current) {
                          kLineChartInstance.current.dispose();
                          kLineChartInstance.current = null;
                        }
                        setShowKLineChart(false);
                        setSelectedStock('');
                        setKLineData([]);
                      }}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: '#999',
                        fontSize: '16px',
                        lineHeight: '1',
                        padding: '0',
                        width: '20px',
                        height: '20px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                    >
                      ×
                    </button>
                  </div>
                  <Spin spinning={kLineLoading} tip="加载K线数据...">
                    <div
                      ref={kLineChartRef}
                      style={{
                        width: '100%',
                        height: 300,
                        minHeight: 300,
                        background: '#fff',
                        borderRadius: 8
                      }}
                    />
                  </Spin>
                </div>
              </div>
            )}

            <div style={{ flex: 1, overflow: 'auto', padding: '8px' }}>
              <Table
                columns={stockColumns}
                dataSource={sortedStocks}
                rowKey="stock_code"
                pagination={false}
                size="small"
                loading={stockLoading}
                scroll={{ y: 'calc(100vh - 600px)' }}
                locale={{
                  emptyText: selectedSector ? '暂无个股数据' : '请选择概念板块'
                }}
                rowClassName={(record: any) =>
                  record && record.stock_code === selectedStock ? 'ant-table-row-hover-selected' : ''
                }
                onRow={(record) => ({
                  onClick: () => handleStockClick(record)
                })}
                style={{ tableLayout: 'auto' }}
              />
            </div>

            </Card>
        </div>
      </div>
    </div>
  );
};

export default Sector;