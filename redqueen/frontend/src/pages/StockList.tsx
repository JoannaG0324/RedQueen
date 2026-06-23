import React, { useState, useEffect, useRef } from 'react';
import { Button, Table, message, Space, Typography, Select, Input, Card, Radio, Drawer, Switch, Spin } from 'antd';
import type { ColumnType } from 'antd/es/table';
import { CalendarOutlined, RocketOutlined, SendOutlined, UserOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { getStockList, getStockKLineData, getLatestTradingDay, analyzeOpportunityStocks as analyzeOpportunityStocksAPI, getSkills, getFavoriteList, upsertFavorite, getFavoriteOne } from '../api/api';

const MARKET_OPTIONS = [
  { value: 'SH_60', label: 'SH_60', prefixes: ['60'] },
  { value: 'SH_688', label: 'SH_688', prefixes: ['688'] },
  { value: 'SZ_0', label: 'SZ_0', prefixes: ['00'] },
  { value: 'SZ_3', label: 'SZ_3', prefixes: ['30'] },
  { value: 'BJ', label: 'BJ', prefixes: ['920'] },
];

const matchMarket = (stockCode: string, selectedMarkets: string[]): boolean => {
  if (!selectedMarkets || selectedMarkets.length === 0) return true;
  const code = stockCode || '';
  return selectedMarkets.some((m) => {
    const opt = MARKET_OPTIONS.find((o) => o.value === m);
    if (!opt) return false;
    return opt.prefixes.some((p) => code.startsWith(p));
  });
};

interface StockData {
  date: string;
  stock_code: string;
  stock_name: string;
  close: number;
  change_rate: number;
  chg_pct_5?: number;
  chg_pct_20?: number;
  growth_streak_days: number;
  growth_streak_pct: number;
  market_cap_r?: number;
  volume_pct?: number;
  turnover?: number;
  industry?: string;
}

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

const SENTIMENT_OPTIONS = [
  { value: '0', label: '0 ' },
  { value: '1', label: '1 ' },
  { value: '2', label: '2 ' },
  { value: '3', label: '3 ' },
  { value: '4', label: '4 ' },
  { value: '5', label: '5 ' },
  { value: '5+', label: '5+ ' },
];

const matchSentiment = (days: any, sentiment: string): boolean => {
  if (!sentiment) return true;
  const d = typeof days === 'number' ? days : parseFloat(days) || 0;
  switch (sentiment) {
    case '0':
      return d >= 0 && d < 1;
    case '1':
      return d >= 1 && d < 2;
    case '2':
      return d >= 2 && d < 3;
    case '3':
      return d >= 3 && d < 4;
    case '4':
      return d >= 4 && d < 5;
    case '5':
      return d >= 5 && d < 6;
    case '5+':
      return d >= 6;
    default:
      return true;
  }
};

const matchKeyword = (stock: StockData, keyword: string): boolean => {
  if (!keyword) return true;
  const kw = keyword.toLowerCase();
  const name = (stock.stock_name || '').toLowerCase();
  const code = (stock.stock_code || '').toLowerCase();
  return name.includes(kw) || code.includes(kw);
};

interface FilterOptions {
  industry?: string;
  sentiment?: string;
  keyword?: string;
  markets?: string[];
  favoriteOnly?: boolean;
  favStockCodes?: Set<string>;
}

const applyFilters = (list: StockData[], opts: FilterOptions): StockData[] => {
  return list.filter((stock) => {
    if (opts.industry && stock.industry !== opts.industry) return false;
    if (!matchSentiment(stock.growth_streak_days, opts.sentiment || '')) return false;
    if (!matchKeyword(stock, opts.keyword || '')) return false;
    if (!matchMarket(stock.stock_code, opts.markets || [])) return false;
    if (opts.favoriteOnly && opts.favStockCodes && !opts.favStockCodes.has(stock.stock_code)) return false;
    return true;
  });
};

const { Title, Text } = Typography;

interface ChatMessage {
  id: string;
  type: 'user' | 'system';
  content: string;
  skillUsed?: string;
  timestamp: Date;
}

interface SkillInfo {
  name: string;
  version: string;
  description: string;
}

interface AnalysisHistory {
  id: string;
  prompt: string;
  stockCodes: string[];
  skillUsed: string;
  timestamp: Date;
}

const StockList: React.FC = () => {
  // latestTradingDate / selectedDate 默认从后端拉取数据库中最新交易日，
  // 避免用"今天"拉到空数据；用户在列表中点击的仍是后端里真实存在的日期。
  const todayStr = new Date().toISOString().split('T')[0];

  const [loading, setLoading] = useState(false);
  const [kLineLoading, setKLineLoading] = useState(false);
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [filteredStocks, setFilteredStocks] = useState<StockData[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(todayStr);
  const [latestTradingDate, setLatestTradingDate] = useState<string>(todayStr);
  const [selectedIndustry, setSelectedIndustry] = useState<string | undefined>(undefined);
  const [selectedMarkets, setSelectedMarkets] = useState<string[]>(MARKET_OPTIONS.map((o) => o.value));
  const [industries, setIndustries] = useState<string[]>([]);
  const [selectedStock, setSelectedStock] = useState<string>('');
  const [kLineData, setKLineData] = useState<KLineData[]>([]);
  const [timeRange, setTimeRange] = useState<string>('90');
  const [stockNames, setStockNames] = useState<Record<string, string>>({});
  const [selectedSentiment, setSelectedSentiment] = useState<string | undefined>(undefined);
  const [stockNameFilter, setStockNameFilter] = useState<string>('');
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [aiInput, setAiInput] = useState<string>('');
  const [aiLoading, setAiLoading] = useState<boolean>(false);
  const [aiStockCodes, setAiStockCodes] = useState<string[]>([]);
  const [aiApplied, setAiApplied] = useState<boolean>(false);

  // 对话相关状态
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<string>('opportunity_analysis');

  // 分析历史记录
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisHistory[]>([]);
  const [showLatestDateKLine, setShowLatestDateKLine] = useState<boolean>(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const kLineRequestId = useRef<number>(0);
  const kLineEndDateRef = useRef<string>('');

  // 收藏相关状态
  const [favStockCodes, setFavStockCodes] = useState<Set<string>>(new Set());
  const [onlyFavorites, setOnlyFavorites] = useState<boolean>(false);
  const [selectedStockFavoriteInfo, setSelectedStockFavoriteInfo] = useState<{ price_date: string | null; status: number } | null>(null);

  // 从后端加载收藏列表（组件首次挂载时）
  const loadFavorites = async () => {
    try {
      const list = await getFavoriteList();
      const favSet = new Set<string>();
      for (const item of list) {
        if (item && item.status === 1) {
          favSet.add(item.stock_code);
        }
      }
      setFavStockCodes(favSet);
    } catch (e: any) {
      console.error('加载收藏列表失败:', e);
      message.error('加载收藏列表失败');
    }
  };

  // 点击星标：收藏或取消收藏
  const toggleFavorite = async (stockCode: string) => {
    const currentlyFav = favStockCodes.has(stockCode);
    const nextStatus = currentlyFav ? 0 : 1;
    const payload: { price_date?: string; status: number } = { status: nextStatus };
    if (nextStatus === 1) {
      // 收藏时把当前查询日期作为 price_date 写入
      payload.price_date = selectedDate || new Date().toISOString().split('T')[0];
    }
    try {
      await upsertFavorite(stockCode, payload);
      const next = new Set(favStockCodes);
      if (nextStatus === 1) {
        next.add(stockCode);
      } else {
        next.delete(stockCode);
      }
      setFavStockCodes(next);
      // 若处于"只看收藏"模式，且取消了收藏，需要实时更新 filteredStocks
      if (onlyFavorites || selectedIndustry || selectedSentiment || stockNameFilter) {
        setFilteredStocks(applyFilters(stocks, {
          industry: selectedIndustry,
          sentiment: selectedSentiment,
          keyword: stockNameFilter,
          markets: selectedMarkets,
          favoriteOnly: onlyFavorites,
          favStockCodes: next,
        }));
      }
      // 如果操作的是当前选中的股票，更新收藏信息
      if (stockCode === selectedStock) {
        setSelectedStockFavoriteInfo({
          price_date: nextStatus === 1 ? payload.price_date || null : null,
          status: nextStatus,
        });
      }
    } catch (e: any) {
      console.error('更新收藏失败:', e);
      message.error('更新收藏失败');
    }
  };

  const clearChart = () => {
    if (chartInstance.current) {
      chartInstance.current.clear();
    }
  };

  // 获取股票列表 - date 为空时后端会自动 fallback 到数据库中最新交易日
  const fetchStocks = async (date?: string, stockCodes: string[] = []) => {
    console.log('调用getStockList，股票代码:', stockCodes);
    setLoading(true);
    try {
      // 总是拉取整份数据，由前端统一做筛选
      const data = await getStockList(date ?? '', '', stockCodes);
      console.log('后端返回的数据:', data);

      // 提取行业列表
      const industrySet = new Set<string>();
      data.forEach((stock: StockData) => {
        if (stock.industry) {
          industrySet.add(stock.industry);
        }
      });
      setIndustries(Array.from(industrySet).sort());

      // 构建股票代码到名称的映射
      const names: Record<string, string> = {};
      data.forEach((stock: StockData) => {
        names[stock.stock_code] = stock.stock_name;
      });
      setStockNames(names);

      setStocks(data);
      setFilteredStocks(applyFilters(data, {
        industry: selectedIndustry,
        sentiment: selectedSentiment,
        keyword: stockNameFilter,
        markets: selectedMarkets,
        favoriteOnly: onlyFavorites,
        favStockCodes: favStockCodes,
      }));
    } catch (error) {
      message.error('获取股票列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 初始化 ECharts 实例
  const initChart = () => {
    console.log('Initializing chart...');
    console.log('chartRef.current:', chartRef.current);
    if (chartRef.current && !chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
      console.log('Chart instance created:', chartInstance.current);
    }
  };

  // 渲染 K 线图
  const renderKLineChart = (data: KLineData[] = kLineData, startPercent: number = 0, endPercent: number = 100) => {
    console.log('Rendering K line chart...');
    console.log('chartInstance.current:', chartInstance.current);
    console.log('Data type:', typeof data, 'Is array:', Array.isArray(data));
    console.log('Zoom range:', startPercent, '% to', endPercent, '%');
    
    // 确保 ECharts 实例已经初始化
    if (!chartInstance.current && chartRef.current) {
      chartInstance.current = echarts.init(chartRef.current);
      console.log('Chart instance created:', chartInstance.current);
    }
    
    // 确保数据是数组且不为空
    if (!chartInstance.current || !Array.isArray(data) || data.length === 0) return;

    // 确保图表容器有正确的尺寸
    if (chartRef.current) {
      const container = chartRef.current;
      const rect = container.getBoundingClientRect();
      console.log('Chart container dimensions:', rect.width, 'x', rect.height);
      
      // 确保容器有最小高度
      if (rect.height < 400) {
        container.style.minHeight = '400px';
        // 重新获取尺寸
        const newRect = container.getBoundingClientRect();
        console.log('Updated chart container dimensions:', newRect.width, 'x', newRect.height);
      }
    }

    // 转换数据格式为 ECharts 需要的格式
    const convertedData = data.map(item => [
      item.date,
      parseFloat(item.open as any) || 0,
      parseFloat(item.close as any) || 0,
      parseFloat(item.low as any) || 0,
      parseFloat(item.high as any) || 0
    ]);

    // 提取成交量数据
    const volumeData = data.map(item => [
      item.date,
      item.volume ? parseFloat(item.volume as any) : 0
    ]);
    
    // 提取 MA 数据
    const ma5Data = data.map(item => [
      item.date,
      item.ma5 !== null ? parseFloat(item.ma5 as any) : null
    ]);
    const ma10Data = data.map(item => [
      item.date,
      item.ma10 !== null ? parseFloat(item.ma10 as any) : null
    ]);
    const ma20Data = data.map(item => [
      item.date,
      item.ma20 !== null ? parseFloat(item.ma20 as any) : null
    ]);
    const ma60Data = data.map(item => [
      item.date,
      item.ma60 !== null ? parseFloat(item.ma60 as any) : null
    ]);

    // N 周期高/低点计算（H20/H60/H120, L20）
    // 语义：到当前交易日为止，回看近 N 个交易日的最高价 / 最低价
    const computeRollingHighLow = (items: any, period: number) => {
      const highs: (number | null)[] = [];
      const lows: (number | null)[] = [];
      for (let i = 0; i < items.length; i++) {
        const start = Math.max(0, i - period + 1);
        let h = -Infinity;
        let l = Infinity;
        let valid = false;
        for (let j = start; j <= i; j++) {
          const hj = parseFloat(items[j].high);
          const lj = parseFloat(items[j].low);
          if (!isNaN(hj) && hj > h) h = hj;
          if (!isNaN(lj) && lj < l) l = lj;
          valid = true;
        }
        highs.push(valid ? h : null);
        lows.push(valid ? l : null);
      }
      return { highs, lows };
    };

    const periods = [20, 60, 120];
    const hlByPeriod: Record<number, { highs: (number | null)[]; lows: (number | null)[] }> = {};
    periods.forEach((p) => {
      hlByPeriod[p] = computeRollingHighLow(data, p);
    });
    
    const option = {
      tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'cross',
            crossStyle: {
              color: '#999'
            }
          },
          position: function(point: any) {
            // 调整提示框的位置，显示在鼠标左侧，避免显示在屏幕边缘
            return [point[0] - 250, point[1] + 10];
          },
          textStyle: {
            textAlign: 'left'
          },
          formatter: function(params: any) {
            if (!params || !params.length) return '';
            
            // 找到 K 线数据
            let klineData: any = null;
            let name: string = '';
            let dataIndex: number = -1;
            
            // 遍历所有参数，找到需要的数据
            for (const item of params) {
              if (item.seriesName === 'K 线') {
                klineData = item.data;
                name = item.name;
                dataIndex = item.dataIndex;
                break;
              }
            }
            
            if (!klineData || dataIndex === -1) return '';
            
            // 从原始数据中获取成交量、成交额和 MA 数据
            const stockData = data[dataIndex];
            const volume = stockData.volume ? stockData.volume.toFixed(2) : '0.00';
            const amount = stockData.amount ? stockData.amount.toFixed(2) : '0.00';
            const ma5 = stockData.ma5 ? stockData.ma5.toFixed(2) : '0.00';
            const ma10 = stockData.ma10 ? stockData.ma10.toFixed(2) : '0.00';
            const ma20 = stockData.ma20 ? stockData.ma20.toFixed(2) : '0.00';
            const ma60 = stockData.ma60 ? stockData.ma60.toFixed(2) : '0.00';
            
            const open = klineData[1] || 0;
            const close = klineData[2] || 0;
            const low = klineData[3] || 0;
            const high = klineData[4] || 0;
            const changeRateValue = typeof stockData.change_rate === 'number' ? stockData.change_rate : parseFloat(stockData.change_rate) || 0;
            const changeRate = changeRateValue.toFixed(2);
            const changeRateColor = changeRateValue >= 0 ? '#ef232a' : '#11c26d';

            return `日期: ${name}<br/>
                   开盘: ${open.toFixed(2)}<br/>
                   收盘: ${close.toFixed(2)}<br/>
                   最低: ${low.toFixed(2)}<br/>
                   最高: ${high.toFixed(2)}<br/>
                   涨跌幅: <span style="color: ${changeRateColor}">${changeRateValue >= 0 ? '+' : ''}${changeRate}%</span><br/>
                   MA5: ${ma5} <br/>
                   MA10: ${ma10} <br/>
                   MA20: ${ma20} <br/>
                   MA60: ${ma60}<br/>
                   H20: ${(hlByPeriod[20].highs[dataIndex] ?? 0).toFixed(2)} / L20: ${(hlByPeriod[20].lows[dataIndex] ?? 0).toFixed(2)}<br/>
                   H60: ${(hlByPeriod[60].highs[dataIndex] ?? 0).toFixed(2)}<br/>
                   H120: ${(hlByPeriod[120].highs[dataIndex] ?? 0).toFixed(2)}<br/>
                   成交量: ${volume}<br/>
                   成交额: ${amount}`;
          }
        },
      legend: [
        {
          data: [
            { name: 'K 线', itemStyle: { color: '#ef232a' } },
            { name: 'MA5', itemStyle: { color: '#4874CB' } },
            { name: 'MA10', itemStyle: { color: '#B68D01' } },
            { name: 'MA20', itemStyle: { color: '#BD5AFF' } },
            { name: 'MA60', itemStyle: { color: '#689EFF' } },
            { name: '成交量', itemStyle: { color: '#ef232a' } }
          ],
          top: 0,
          left: 0,
          align: 'left'
        },
        {
          data: [
            { name: 'H20', itemStyle: { color: '#ef232a' } },
            { name: 'H60', itemStyle: { color: '#FF01FF' } },
            { name: 'H120', itemStyle: { color: '#9d0208' } },
            { name: 'L20', itemStyle: { color: '#0b140dff' } }
          ],
          top: 5,
          right: 0,
          align: 'left'
        }
      ],
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
          showDetail: true // 隐藏滑块文字，防止溢出
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
          data: data.map(item => item.date),
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
          data: data.map(item => item.date),
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
          },
          markLine: {
            symbol: 'none',
            silent: true,
            lineStyle: {
              type: 'dashed',
              color: '#1890ff',
              width: 1.2
            },
            label: {
              formatter: (params: any) => `${params.name || ''}`,
              color: '#1890ff'
            },
            data: (() => {
              const markDate = kLineEndDateRef.current || selectedDate;
              if (!markDate) return [];
              return [{ xAxis: markDate, name: markDate }];
            })()
          }
        },
        {
          name: 'MA5',
          type: 'line',
          data: ma5Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 0.8,
            color: '#4874CB' // 蓝色
          },
          symbol: 'none'
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 0.8,
            color: '#B68D01' // 黄色
          },
          symbol: 'none'
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 0.8,
            color: '#BD5AFF' // 紫紫色
          },
          symbol: 'none'
        },
        {
          name: 'MA60',
          type: 'line',
          data: ma60Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 0.8,
            color: '#689EFF' // 蓝紫色
          },
          symbol: 'none'
        },
        // N 周期高/低点：红色系高点 + 绿色系低点，随周期增长颜色加深，虚线
        {
          name: 'H20',
          type: 'line',
          data: hlByPeriod[20].highs,
          smooth: false,
          showSymbol: false,
          symbol: 'none',
          lineStyle: { width: 1, color: '#ef232a', type: 'dashed' }
        },
        {
          name: 'H60',
          type: 'line',
          data: hlByPeriod[60].highs,
          smooth: false,
          showSymbol: false,
          symbol: 'none',
          lineStyle: { width: 1, color: '#FF01FF', type: 'dashed' }
        },
        {
          name: 'H120',
          type: 'line',
          data: hlByPeriod[120].highs,
          smooth: false,
          showSymbol: false,
          symbol: 'none',
          lineStyle: { width: 1, color: '#9d0208', type: 'dashed' }
        },
        {
          name: 'L20',
          type: 'line',
          data: hlByPeriod[20].lows,
          smooth: false,
          showSymbol: false,
          symbol: 'none',
          lineStyle: { width: 1, color: '#0b140dff', type: 'dashed' }
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

    chartInstance.current.setOption(option);
    chartInstance.current.resize();
  };

  // 获取股票 K 线数据
  // markLineDate: 垂直辅助线的日期，与作图 endDate 解耦（Switch 切换不影响辅助线位置）
  const fetchKLineData = async (
    stockCode: string,
    _days: number = 20,
    endDate: string = selectedDate,
    markLineDate: string = selectedDate,
  ) => {
    // 总是获取所有可用数据，用于支持完整的缩放功能（传入的 days 仅作签名占位）
    const validDays = 9999; // 使用大值确保获取所有数据
    const myReqId = ++kLineRequestId.current;
    kLineEndDateRef.current = markLineDate;
    console.log('Fetching K line data for:', stockCode, 'endDate:', endDate, 'markLineDate:', markLineDate, 'reqId:', myReqId);
    setKLineLoading(true);
    try {
      let data = await getStockKLineData(stockCode, validDays, endDate);
      // 兜底：当指定 endDate 返回空数据（例如上市天数不足 / 数据尚未入库）时，
      // 再尝试一次"不指定 endDate"请求，让后端用最新交易日回退，尽可能画出图
      if ((!Array.isArray(data) || data.length === 0) && endDate) {
        console.log('Primary endDate returned empty, retry without end_date for:', stockCode);
        const fallback = await getStockKLineData(stockCode, validDays, '');
        if (myReqId !== kLineRequestId.current) {
          console.log('Discard stale fallback K line response for reqId:', myReqId);
          return;
        }
        data = fallback;
      } else if (myReqId !== kLineRequestId.current) {
        console.log('Discard stale K line response for reqId:', myReqId);
        return;
      }
      console.log('K line data received:', data);
      setKLineData(data);
      if (!Array.isArray(data) || data.length === 0) {
        // 后端返回空数据时，主动清空旧图，避免永远卡在之前的股票图形
        clearChart();
      }
    } catch (error) {
      if (myReqId !== kLineRequestId.current) return;
      console.error('Error fetching K line data:', error);
      message.error('获取 K 线数据失败');
      clearChart();
    } finally {
      if (myReqId !== kLineRequestId.current) return;
      setKLineLoading(false);
    }
  };

  // 组件挂载时初始化 ECharts 实例
  useEffect(() => {
    initChart();
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  // 窗口大小变化时调整图表大小
  useEffect(() => {
    const handleResize = () => {
      if (chartInstance.current) {
        chartInstance.current.resize();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // K 线数据变化或目标日变化时更新图表（markLine 依赖 selectedDate）
  useEffect(() => {
    if (Array.isArray(kLineData) && kLineData.length > 0) {
      const displayDays = timeRange === 'ALL' ? 365 : parseInt(timeRange);
      const startIndex = Math.max(0, kLineData.length - displayDays);
      const startPercent = (startIndex / kLineData.length) * 100;
      const endPercent = 100;
      renderKLineChart(kLineData, startPercent, endPercent);
    } else if (selectedStock) {
      clearChart();
    }
  }, [kLineData, timeRange, selectedStock, selectedDate]);

  // 日期变化处理 - 重新拉取全量数据
  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      setSelectedIndustry('');
      setAiApplied(false);
      fetchStocks(newDate);

      // 如果已经选择了股票，重新获取K线图数据，使用新的日期作为结束日期
      if (selectedStock) {
        // 切换日期时先重置 K 线图状态，避免显示旧日期的数据
        setKLineData([]);
        clearChart();
        setKLineLoading(true);
        fetchKLineData(selectedStock, parseInt(timeRange), newDate);
      }
    }
  };

  // 行业变化处理 - 纯前端筛选
  const handleIndustryChange = (value: string | null) => {
    const industry = value ;
    setSelectedIndustry(industry);
    setFilteredStocks(applyFilters(stocks, {
      industry,
      sentiment: selectedSentiment,
      keyword: stockNameFilter,
      markets: selectedMarkets,
      favoriteOnly: onlyFavorites,
      favStockCodes: favStockCodes,
    }));
  };

  // Sentiment 变化处理 - 纯前端筛选
  const handleSentimentChange = (value: string | null) => {
    const sentiment = value ;
    setSelectedSentiment(sentiment);
    setFilteredStocks(applyFilters(stocks, {
      industry: selectedIndustry,
      sentiment,
      keyword: stockNameFilter,
      markets: selectedMarkets,
      favoriteOnly: onlyFavorites,
      favStockCodes: favStockCodes,
    }));
  };

  // 股票名称/代码过滤变化处理 - 纯前端筛选
  const handleStockNameFilterChange = (value: string) => {
    setStockNameFilter(value);
    setFilteredStocks(applyFilters(stocks, {
      industry: selectedIndustry,
      sentiment: selectedSentiment,
      keyword: value,
      markets: selectedMarkets,
      favoriteOnly: onlyFavorites,
      favStockCodes: favStockCodes,
    }));
  };

  // 市场筛选变化处理 - 纯前端筛选
  const handleMarketsChange = (value: string[]) => {
    setSelectedMarkets(value);
    setFilteredStocks(applyFilters(stocks, {
      industry: selectedIndustry,
      sentiment: selectedSentiment,
      keyword: stockNameFilter,
      markets: value,
      favoriteOnly: onlyFavorites,
      favStockCodes: favStockCodes,
    }));
  };

  // 重置所有 applyFilters 相关的筛选条件（行业 / 情绪 / 名称代码 / 市场）
  const resetFilters = () => {
    setSelectedIndustry('');
    setSelectedSentiment('');
    setStockNameFilter('');
    setSelectedMarkets(MARKET_OPTIONS.map((o) => o.value));
    // 仅重置 applyFilters 相关筛选；是否仅看收藏由 Switch 独立控制
    setFilteredStocks(applyFilters(stocks, {
      favoriteOnly: onlyFavorites,
      favStockCodes: favStockCodes,
    }));
  };

  // 仅看收藏开关变化处理
  const handleOnlyFavoritesChange = (checked: boolean) => {
    setOnlyFavorites(checked);
    setFilteredStocks(applyFilters(stocks, {
      industry: selectedIndustry,
      sentiment: selectedSentiment,
      keyword: stockNameFilter,
      markets: selectedMarkets,
      favoriteOnly: checked,
      favStockCodes: favStockCodes,
    }));
  };

  // 清除AI分析结果
  const clearAiAnalysis = () => {
    setAiApplied(false);
    fetchStocks(selectedDate);
    message.success('已清除AI分析结果');
  };

  // 应用AI分析结果到查询
  const applyAiAnalysis = () => {
    if (aiStockCodes.length > 0) {
      console.log('应用AI分析结果，股票代码:', aiStockCodes);
      fetchStocks(selectedDate, aiStockCodes);
      setDrawerVisible(false);
      setAiApplied(true);
      message.success(`Apply ${aiStockCodes.length} opportunities`);
    } else {
      message.warning('请先进行AI分析获取股票代码');
    }
  };

  // 应用历史分析结果到查询
  const applyHistoryAnalysis = (stockCodes: string[], prompt: string) => {
    console.log('应用历史分析结果，股票代码:', stockCodes);
    setAiStockCodes(stockCodes);
    fetchStocks(selectedDate, stockCodes);
    setDrawerVisible(false);
    setAiApplied(true);
    message.success(`已应用历史分析: "${prompt.substring(0, 30)}..."`);
  };

  // 删除历史记录
  const deleteHistoryItem = (id: string) => {
    setAnalysisHistory(prev => prev.filter(item => item.id !== id));
    message.success('已删除历史记录');
  };

  // 股票选择处理 - 选新股票前先清空旧图并显示loading，避免"先坍缩再渲染"
  const handleStockSelect = async (stockCode: string) => {
    console.log('Selected stock:', stockCode);
    setSelectedStock(stockCode);
    setKLineLoading(true);
    clearChart();
    const kLineEndDate = showLatestDateKLine ? latestTradingDate : selectedDate;
    fetchKLineData(stockCode, parseInt(timeRange), kLineEndDate);
    try {
      const favInfo = await getFavoriteOne(stockCode);
      setSelectedStockFavoriteInfo({
        price_date: favInfo.price_date,
        status: favInfo.status,
      });
    } catch (e: any) {
      console.error('获取收藏状态失败:', e);
      setSelectedStockFavoriteInfo(null);
    }
  };

  // 时间范围变化处理 - 切换周期前先清空旧图并显示loading，避免"先坍缩再渲染"
  const handleTimeRangeChange = (value: string) => {
    setTimeRange(value);
    if (selectedStock) {
      setKLineLoading(true);
      if (chartInstance.current) {
        chartInstance.current.clear();
      }
      const kLineEndDate = showLatestDateKLine ? latestTradingDate : selectedDate;
      fetchKLineData(selectedStock, parseInt(value), kLineEndDate);
    }
  };

  // 调用AI分析（对话形式）
  const analyzeOpportunityStocks = async () => {
    if (!aiInput.trim()) {
      message.warning('请输入分析内容');
      return;
    }
    
    setAiLoading(true);
    
    // 添加用户消息到对话历史
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: aiInput,
      timestamp: new Date()
    };
    setChatMessages(prev => [...prev, userMessage]);
    
    try {
      // 调用AI分析（传递选中的Skill）
      const result = await analyzeOpportunityStocksAPI(aiInput, selectedSkill);
      
      // 添加系统响应到对话历史
      const systemMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'system',
        content: result.analysis,
        skillUsed: result.metadata?.skill_name || selectedSkill,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, systemMessage]);
      
      // 使用后端返回的stock_list字段（已自动提取股票代码）
      const stockCodes = result.stock_list || [];
      
      // 保存到历史记录（只保存有股票代码的结果）
      if (stockCodes.length > 0) {
        const historyItem: AnalysisHistory = {
          id: Date.now().toString(),
          prompt: aiInput,
          stockCodes: stockCodes,
          skillUsed: result.metadata?.skill_name || selectedSkill,
          timestamp: new Date()
        };
        setAnalysisHistory(prev => [historyItem, ...prev]);
        
        setAiStockCodes(stockCodes);
        message.success(`Analysis Complete. ${stockCodes.length} opportunities identified.`);
      } else {
        message.error('未找到股票代码');
        setAiStockCodes([]);
      }
    } catch (error: any) {
      console.error('AI分析失败:', error);
      // 添加错误消息到对话历史
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        type: 'system',
        content: `分析失败: ${error.response?.data?.detail || '请稍后重试'}`,
        timestamp: new Date()
      };
      setChatMessages(prev => [...prev, errorMessage]);
      
      if (error.response && error.response.data && error.response.data.detail) {
        message.error(`AI分析失败: ${error.response.data.detail}`);
      } else {
        message.error('AI分析失败，请稍后重试');
      }
    } finally {
      setAiInput('');
      setAiLoading(false);
    }
  };

  // 加载Skill列表
  useEffect(() => {
    const loadSkills = async () => {
      try {
        const skillsData = await getSkills();
        setSkills(skillsData);
      } catch (error) {
        console.error('加载Skill列表失败:', error);
      }
    };
    loadSkills();
  }, []);

  // 组件初始化时加载数据：
  // 1) 先向后端拉"最新交易日"，避免用"今天"拿到空数据；
  // 2) 再用该日期（或不传让后端 fallback）拉全量列表。
  useEffect(() => {
    const initData = async () => {
      try {
        const latest = await getLatestTradingDay();
        const latestDate = (latest && latest.date) || todayStr;
        setLatestTradingDate(latestDate);
        setSelectedDate(latestDate);
      } catch (error) {
        console.error('获取最新交易日失败，回退为今天:', error);
      }
      loadFavorites();
      fetchStocks('', aiApplied ? aiStockCodes : undefined);
    };
    initData();
  }, []);

  // 表格列定义
  const columns: ColumnType<StockData>[] = [
    {
      title: 'Fav',
      key: 'favorite',
      width: 60,
      align: 'center',
      fixed: 'left',
      render: (_: any, record: any) => {
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
      },
    },
    {
      title: 'Code',
      dataIndex: 'stock_code',
      key: 'stock_code',
      width: 100,
      align: 'center',
      render: (text: string) => (
        <a onClick={() => handleStockSelect(text)}>{text}</a>
      ),
    },
    {
      title: 'Name',
      dataIndex: 'stock_name',
      key: 'stock_name',
      minWidth: 100,
      align: 'center',
    },
    {
      title: 'Industry',
      dataIndex: 'industry',
      key: 'industry',
      width: 150,
      align: 'center',
      sorter: (a: any, b: any) => {
        const strA = a.industry ?? '';
        const strB = b.industry ?? '';
        return strA.localeCompare(strB, 'zh-CN'); // 中文汉字按拼音排序
      },      
      render: (text: any) => text || '未知',
    },
    {
      title: 'Close',
      dataIndex: 'close',
      key: 'close',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => (a.close || 0) - (b.close || 0),
      render: (text: any) => typeof text === 'number' ? text.toFixed(2) : '0.00',
    },
    {
      title: 'Chg%',
      dataIndex: 'change_rate',
      key: 'change_rate',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => {
        const valA = typeof a.change_rate === 'number' ? a.change_rate : parseFloat(a.change_rate) || 0;
        const valB = typeof b.change_rate === 'number' ? b.change_rate : parseFloat(b.change_rate) || 0;
        return valA - valB;
      },
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d'   }}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: '5Chg%',
      dataIndex: 'chg_pct_5',
      key: 'chg_pct_5',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => {
        const valA = typeof a.chg_pct_5 === 'number' ? a.chg_pct_5 : parseFloat(a.chg_pct_5) || 0;
        const valB = typeof b.chg_pct_5 === 'number' ? b.chg_pct_5 : parseFloat(b.chg_pct_5) || 0;
        return valA - valB;
      },
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d'   }}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: '20Chg%',
      dataIndex: 'chg_pct_20',
      key: 'chg_pct_20',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => {
        const valA = typeof a.chg_pct_20 === 'number' ? a.chg_pct_20 : parseFloat(a.chg_pct_20) || 0;
        const valB = typeof b.chg_pct_20 === 'number' ? b.chg_pct_20 : parseFloat(b.chg_pct_20) || 0;
        return valA - valB;
      },
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d'   }}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'Turnover%',
      dataIndex: 'turnover',
      key: 'turnover',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => (a.turnover || 0) - (b.turnover || 0),
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text>
            {value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'Days',
      dataIndex: 'growth_streak_days',
      key: 'growth_streak_days',
      width: 80,
      align: 'right',
      sorter: (a: any, b: any) => (a.growth_streak_days || 0) - (b.growth_streak_days || 0),
    },
    {
      title: 'Days%',
      dataIndex: 'growth_streak_pct',
      key: 'growth_streak_pct',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => (a.growth_streak_pct || 0) - (b.growth_streak_pct || 0),
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text>
            {value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'Cup(0.1B)',
      dataIndex: 'market_cap_r',
      key: 'market_cap_r',
      width: 120,
      align: 'right',
      sorter: (a: any, b: any) => (a.market_cap_r || 0) - (b.market_cap_r || 0),
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        return (
          <Text>
            {(value / 100000000).toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'Volume%',
      dataIndex: 'volume_pct',
      key: 'volume_pct',
      width: 100,
      align: 'right',
      sorter: (a: any, b: any) => (a.volume_pct || 0) - (b.volume_pct || 0),
      render: (text: any) => {
        const value = typeof text === 'number' ? text : parseFloat(text) || 0;
        const color = value >= 0 ? '#ef232a' : '#11c26d';
        return (
          <Text style={{ color: color }}>
            {value >= 0 ? '+' : ''}{value.toFixed(2)}
          </Text>
        );
      },
    },
  ];

  // 处理窗口大小变化，调整 ECharts 图表大小
  useEffect(() => {
    const handleResize = () => {
      if (chartInstance.current) {
        chartInstance.current.resize();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: '800px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => handleDateChange(e.target.value)}
          style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '32px', marginRight: '12px' }}
        />
        <Select
          mode="multiple"
          placeholder="By Market"
          style={{ width: 200, marginRight: '12px' }}
          value={selectedMarkets}
          onChange={handleMarketsChange}
          maxTagCount="responsive"
          options={MARKET_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <Select
          placeholder="By Industry"
          style={{ width: 150, marginRight: '12px' }}
          value={selectedIndustry}
          onChange={handleIndustryChange}
          allowClear
          showSearch
          optionFilterProp="label"
          filterOption={(input, option) =>
            String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
          options={industries.map(industry => ({ label: industry, value: industry }))}
        />
         <Input
          placeholder="By Name or Code"
          style={{ width: 150, marginRight: '12px' }}
          value={stockNameFilter}
          onChange={(e) => handleStockNameFilterChange(e.target.value)}
          allowClear
        />
        <Select
          placeholder="By Sentiment"
          style={{ width: 150, marginRight: '12px' }}
          value={selectedSentiment}
          onChange={handleSentimentChange}
          allowClear
          options={SENTIMENT_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
        />
        {aiApplied && (
          <div style={{ position: 'relative', display: 'inline-block', marginRight: '12px' }}>
            <div style={{ 
              padding: '0 12px', 
              backgroundColor: '#e6f7ff', 
              border: '1px solid #91d5ff', 
              borderRadius: '4px', 
              fontSize: '14px',
              color: '#1890ff',
              display: 'flex',
              alignItems: 'center',
              height: '32px'
            }}>
              AI
              <button 
                onClick={clearAiAnalysis}
                style={{
                  marginLeft: '8px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#1890ff',
                  fontSize: '16px',
                  lineHeight: '1',
                  padding: '0',
                  width: '16px',
                  height: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>
          </div>
        )}
        <Button
          type="default"
          icon={<ReloadOutlined />}
          onClick={resetFilters}
          style={{ marginRight: '12px' }}
        >
          Reset
        </Button>
        <div style={{ marginRight: '12px', display: 'flex', alignItems: 'center' }}>
          <Switch
            checked={onlyFavorites}
            onChange={handleOnlyFavoritesChange}
            checkedChildren="Off"
            unCheckedChildren="Star"
          />
        </div>

        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="default"
            icon={<RocketOutlined />}
            onClick={() => setDrawerVisible(true)}
          >
            Ask AI
          </Button>
        </div>
      </div>

      <div style={{ width: '100%', flex: 1, display: 'flex', gap: 16, overflowX: 'hidden' }}>
        {/* 左侧股票列表 */}
        <div style={{ flex: 5.5, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowX: 'auto' }}>
              <div style={{ minWidth: 600 }}>
                <Table
                  columns={columns}
                  dataSource={filteredStocks}
                  rowKey={(record: any) => `${record.stock_code}-${record.date}`}
                  loading={loading}
                  pagination={{ pageSize: 20 }}
                  size="small"
                  rowClassName={(record: any) =>
                    record && record.stock_code === selectedStock ? 'ant-table-row-hover-selected' : ''
                  }
                  onRow={(record: any) => ({
                    onClick: () => record && record.stock_code && handleStockSelect(record.stock_code)
                  })}
                />
              </div>
            </div>
          </Card>
        </div>

        {/* 右侧 K 线图 */}
        <div style={{ flex: 4.5, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, minWidth: 600, padding: 0, display: 'flex', flexDirection: 'column', minHeight: '600px' }} title={
            <Space>
              {selectedStock ? (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span>{stockNames[selectedStock]} {selectedStock}</span>
                  <a
                    href={(() => {
                      let market = '0';
                      if (selectedStock.startsWith('60') || selectedStock.startsWith('68')) {
                        market = '1';
                      } else if (selectedStock.startsWith('00') || selectedStock.startsWith('30')) {
                        market = '0';
                      }
                      return `https://quote.eastmoney.com/basic/h5chart-iframe.html?code=${selectedStock}&market=${market}&type=r`;
                    })()}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: 'none', color: '#1890ff' }}
                  >
                    分时
                  </a>
                  <a
                    href={`https://www.igu888.com/hangqing/${selectedStock}.html`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: 'none', color: '#1890ff' }}
                  >
                    igu888
                  </a>
                </span>
              ) : 'K LINE'}
              <Radio.Group 
                value={timeRange} 
                onChange={(e) => handleTimeRangeChange(e.target.value)}
                buttonStyle="solid"
              >
                <Radio.Button value="20">20D</Radio.Button>
                <Radio.Button value="60">60D</Radio.Button>
                <Radio.Button value="90">90D</Radio.Button>
                <Radio.Button value="120">120D</Radio.Button>
                <Radio.Button value="ALL">ALL</Radio.Button>
              </Radio.Group>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
                <Switch
                  checked={showLatestDateKLine}
                  onChange={(checked) => {
                    setShowLatestDateKLine(checked);
                    if (selectedStock) {
                      setKLineLoading(true);
                      if (chartInstance.current) {
                        chartInstance.current.clear();
                      }
                      const kLineEndDate = checked ? latestTradingDate : selectedDate;
                      fetchKLineData(selectedStock, parseInt(timeRange), kLineEndDate, selectedDate);
                    }
                  }}
                  checkedChildren="Date"
                  unCheckedChildren="Latest"
                />
              </div>
            </Space>
          }>
            <div style={{ flex: 1, width: '100%', minHeight: '600px' }}>
              {selectedStock ? (
                <Spin
                  spinning={kLineLoading}
                  tip="加载K线数据..."
                  style={{ width: '100%', height: '100%' }}
                >
                  <div ref={chartRef} style={{ width: '100%', height: '100%', minHeight: '400px' }} />
                </Spin>
              ) : (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text>请选择一只股票查看 K 线图</Text>
                </div>
              )}  
              {selectedStock && selectedStockFavoriteInfo && selectedStockFavoriteInfo.status === 1 && selectedStockFavoriteInfo.price_date && (
              <div style={{  paddingTop: '10px', paddingLeft: '80px'}}>
                <Text style={{ fontSize: '14px', color: '#1890ff', fontWeight: 'bold' }}>
                  Focus on {selectedStockFavoriteInfo.price_date}
                </Text>
              </div>
            )}
            </div>
          </Card>
        </div>
      </div>

      {/* AI分析抽屉 */}
      <Drawer
        title="AI分析"
        placement="right"
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        size={600}
      >
        {/* Skill选择器 */}
        <div style={{ marginBottom: '16px' }}>
          <Text type="secondary" style={{ marginRight: '8px' }}>Skill：</Text>
          <Select
            value={selectedSkill}
            onChange={(value) => setSelectedSkill(value)}
            style={{ width: 200 }}
            options={skills.map(skill => ({ label: skill.description, value: skill.name }))}
          />
        </div>

        {/* 对话历史区域 */}
        <div style={{ 
          height: '350px', 
          overflowY: 'auto', 
          border: '1px solid #f0f0f0', 
          borderRadius: '8px',
          padding: '12px',
          marginBottom: '16px',
          backgroundColor: '#fafafa'
        }}>
          {chatMessages.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
              <p>开始对话</p>
            </div>
          ) : (
            <div>
              {chatMessages.map((message) => (
                <div key={message.id} style={{ marginBottom: '16px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                    {message.type === 'user' ? (
                      <>
                        <UserOutlined style={{ fontSize: '20px', marginRight: '8px', color: '#1890ff' }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#1890ff' }}>
                            我
                          </div>
                          <div style={{ backgroundColor: '#1890ff', color: 'white', padding: '8px 12px', borderRadius: '0 8px 8px 8px', maxWidth: '80%' }}>
                            {message.content}
                          </div>
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#52c41a' }}>
                            AI助手 {message.skillUsed && `(${message.skillUsed})`}
                          </div>
                          <div style={{ backgroundColor: '#fff', border: '1px solid #d9d9d9', padding: '8px 12px', borderRadius: '8px 0 8px 8px', maxWidth: '80%' }}>
                            <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', lineHeight: '1.6' }}>
                              {message.content}
                            </div>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {aiLoading && (
                <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                  <div style={{ backgroundColor: '#fff', border: '1px solid #d9d9d9', padding: '8px 12px', borderRadius: '8px 0 8px 8px' }}>
                    <Text type="secondary">思考中...</Text>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 历史记录区域 */}
        {analysisHistory.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <Title level={5} style={{ marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', color: '#666' }}>分析历史</span>
            </Title>
            <div style={{ 
              border: '1px solid #f0f0f0', 
              borderRadius: '8px',
              maxHeight: '200px',
              overflowY: 'auto'
            }}>
              {analysisHistory.map((item) => (
                <div 
                  key={item.id} 
                  style={{ 
                    padding: '10px 12px', 
                    borderBottom: '1px solid #f0f0f0',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13px', color: '#333', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.prompt}
                    </div>
                    <div style={{ fontSize: '11px', color: '#999', marginTop: '4px' }}>
                      {item.stockCodes.length} 只股票 · {item.timestamp.toLocaleString('zh-CN')}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', marginLeft: '12px' }}>
                    <Button 
                      size="small" 
                      onClick={() => applyHistoryAnalysis(item.stockCodes, item.prompt)}
                      type="primary"
                      ghost
                    >
                      应用
                    </Button>
                    <Button 
                      size="small" 
                      onClick={() => deleteHistoryItem(item.id)}
                      danger
                      ghost
                    >
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 输入区域 */}
        <div>
          <Input.TextArea
            placeholder="请输入分析内容"
            value={aiInput}
            onChange={(e) => setAiInput(e.target.value)}
            rows={3}
            style={{ marginBottom: '12px' }}
            onPressEnter={(e) => {
              if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                analyzeOpportunityStocks();
              }
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              提示：Ctrl+Enter 发送
            </Text>
            <Space>
              <Button onClick={applyAiAnalysis} disabled={aiStockCodes.length === 0}>
                应用到查询
              </Button>
              <Button
                type="primary"
                onClick={analyzeOpportunityStocks}
                loading={aiLoading}
                icon={<SendOutlined />}
              >
                发送
              </Button>
            </Space>
          </div>
        </div>
      </Drawer>
    </div>
  );
};

export default StockList;