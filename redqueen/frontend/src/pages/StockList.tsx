import React, { useState, useEffect, useRef } from 'react';
import { Button, Table, message, Space, Typography, Select, Input, Card, Tooltip, Modal, Radio, Drawer, Switch } from 'antd';
import { CalendarOutlined, RocketOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { getStockList, getStockKLineData, getLatestTradingDay, analyzeOpportunityStocks as analyzeOpportunityStocksAPI } from '../api/api';

const { Title, Text } = Typography;

interface StockData {
  date: string;
  stock_code: string;
  stock_name: string;
  close: number;
  change_rate: number;
  growth_streak_days: number;
  growth_streak_pct: number;
  industry?: string;
  total_triggers?: number;
  triggered_rules?: any[];
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

const StockList: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [kLineLoading, setKLineLoading] = useState(false);
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [filteredStocks, setFilteredStocks] = useState<StockData[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [selectedIndustry, setSelectedIndustry] = useState<string | undefined>(undefined);
  const [industries, setIndustries] = useState<string[]>([]);
  const [selectedStock, setSelectedStock] = useState<string>('');
  const [kLineData, setKLineData] = useState<KLineData[]>([]);
  const [timeRange, setTimeRange] = useState<string>('90');
  const [stockNames, setStockNames] = useState<Record<string, string>>({});
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedStockData, setSelectedStockData] = useState<any>(null);
  const [selectedRule, setSelectedRule] = useState<string | undefined>(undefined);
  const [availableRules, setAvailableRules] = useState<string[]>([]);
  const [stockNameFilter, setStockNameFilter] = useState<string>('');
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [aiInput, setAiInput] = useState<string>('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<string>('');
  const [aiStockCodes, setAiStockCodes] = useState<string[]>([]);
  const [aiApplied, setAiApplied] = useState<boolean>(false);
  const [showLatestDateKLine, setShowLatestDateKLine] = useState<boolean>(false); // K线图显示最新日期数据开关
  const [latestTradingDate, setLatestTradingDate] = useState<string>(new Date().toISOString().split('T')[0]); // 实际最新交易日
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // 获取股票列表
  const fetchStocks = async (date: string, industry: string = '', stockCodes: string[] = []) => {
    console.log('调用getStockList，股票代码:', stockCodes);
    setLoading(true);
    try {
      const data = await getStockList(date, industry, stockCodes);
      console.log('后端返回的数据:', data);
      
      // 直接使用后端返回的数据，因为已经在后端进行了过滤
      let filteredByAi = data;
      
      // 提取行业列表
      const industrySet = new Set<string>();
      filteredByAi.forEach(stock => {
        if (stock.industry) {
          industrySet.add(stock.industry);
        }
      });
      setIndustries(Array.from(industrySet).sort());
      
      // 构建股票代码到名称的映射
      const names: Record<string, string> = {};
      filteredByAi.forEach(stock => {
        names[stock.stock_code] = stock.stock_name;
      });
      setStockNames(names);
      
      // 批量获取异动数据
      try {
        const { getAnomalyStocks } = await import('../api/api');
        const anomalyStocks = await getAnomalyStocks(date);
        const anomalyMap: Record<string, any> = {};
        
        if (anomalyStocks) {
          anomalyStocks.forEach((stock: any) => {
            anomalyMap[stock.stock_code] = {
              total_triggers: stock.total_triggers,
              triggered_rules: stock.triggered_rules
            };
          });
        }
        
        // 合并异动数据到股票列表
        const mergedData = filteredByAi.map((stock: any) => ({
          ...stock,
          ...anomalyMap[stock.stock_code]
        }));
        
        // 提取所有可用的规则
        const ruleSet = new Set<string>();
        mergedData.forEach((stock: any) => {
          if (stock.triggered_rules) {
            stock.triggered_rules.forEach((rule: any) => {
              ruleSet.add(rule.rule_chinese_name || rule.rule_name);
            });
          }
        });
        setAvailableRules(Array.from(ruleSet).sort());
        
        setStocks(mergedData);
        // 应用规则筛选和股票名称过滤
        let filtered = mergedData;
        if (selectedRule) {
          filtered = filtered.filter((stock: any) => {
            if (!stock.triggered_rules) return false;
            return stock.triggered_rules.some((rule: any) => 
              (rule.rule_chinese_name || rule.rule_name) === selectedRule
            );
          });
        }
        // 应用股票名称模糊查询
        if (stockNameFilter) {
          const filterLower = stockNameFilter.toLowerCase();
          filtered = filtered.filter((stock: any) => 
            stock.stock_name && stock.stock_name.toLowerCase().includes(filterLower)
          );
        }
        setFilteredStocks(filtered);
      } catch (error) {
        console.error('获取异动数据失败:', error);
        // 如果获取异动数据失败，使用过滤后的数据
        setStocks(filteredByAi);
        setFilteredStocks(filteredByAi);
      }
    } catch (error) {
      message.error('获取股票列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理规则点击事件，显示股票详情弹窗
  const handleRuleClick = (record: any) => {
    setSelectedStockData(record);
    setModalVisible(true);
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
            return [point[0] - 100, point[1] - 10];
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
            const volume = stockData.volume ? parseFloat(stockData.volume).toFixed(2) : '0.00';
            const amount = stockData.amount ? parseFloat(stockData.amount).toFixed(2) : '0.00';
            const ma5 = stockData.ma5 ? parseFloat(stockData.ma5).toFixed(2) : '0.00';
            const ma10 = stockData.ma10 ? parseFloat(stockData.ma10).toFixed(2) : '0.00';
            const ma20 = stockData.ma20 ? parseFloat(stockData.ma20).toFixed(2) : '0.00';
            const ma60 = stockData.ma60 ? parseFloat(stockData.ma60).toFixed(2) : '0.00';
            
            const open = klineData[1] || 0;
            const close = klineData[2] || 0;
            const low = klineData[3] || 0;
            const high = klineData[4] || 0;
            const changeRateValue = open !== 0 ? ((close - open) / open * 100) : 0;
            const changeRate = changeRateValue.toFixed(2);
            const changeRateColor = changeRateValue >= 0 ? '#ef232a' : '#11c26d';
            
            return `日期: ${name}<br/>
                   开盘: ${open.toFixed(2)}<br/>
                   收盘: ${close.toFixed(2)}<br/>
                   最低: ${low.toFixed(2)}<br/>
                   最高: ${high.toFixed(2)}<br/>
                   涨跌幅: <span style="color: ${changeRateColor}">${changeRate}%</span><br/>
                   MA5: ${ma5}<br/>
                   MA10: ${ma10}<br/>
                   MA20: ${ma20}<br/>
                   MA60: ${ma60}<br/>
                   成交量: ${volume}<br/>
                   成交额: ${amount}`;
          }
        },
      legend: {
        data: ['K 线', 'MA5', 'MA10', 'MA20', 'MA60', '成交量']
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
          bottom: 0,
          zoomLock: false
        }
      ],
      grid: [
        {
          left: '3%',
          right: '4%',
          top: '3%',
          height: '60%',
          containLabel: true
        },
        {
          left: '3%',
          right: '4%',
          top: '70%',
          height: '20%',
          containLabel: true
        }
      ],
      xAxis: [
        {
          type: 'category',
          boundaryGap: false,
          data: data.map(item => item.date),
          axisLabel: {
            formatter: function(value: any) {
              return value;
            }
          },
          axisPointer: {
            type: 'shadow'
          },
          axisLine: {
            show: true
          },
          axisTick: {
            show: true
          }
        },
        {
          type: 'category',
          boundaryGap: false,
          data: data.map(item => item.date),
          gridIndex: 1,
          axisLabel: {
            formatter: function(value: any) {
              return value;
            }
          },
          axisLine: {
            show: true
          },
          axisTick: {
            show: true
          }
        }
      ],
      yAxis: [
        {
          type: 'value',
          scale: true,
          splitNumber: 5,
          axisLabel: {
            formatter: function(value: any) {
              return Math.round(value);
            }
          },
          splitArea: {
            show: true,
            areaStyle: {
              color: ['rgba(240, 240, 240, 0.2)', 'rgba(255, 255, 255, 0.2)']
            }
          }
        },
        {
          type: 'value',
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          show: false
        }
      ],
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
            width: 1,
            color: '#ff4d4f' // 红色
          },
          symbol: 'none'
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1,
            color: '#1890ff' // 蓝色
          },
          symbol: 'none'
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1,
            color: '#52c41a' // 绿色
          },
          symbol: 'none'
        },
        {
          name: 'MA60',
          type: 'line',
          data: ma60Data.map(item => item[1]),
          smooth: true,
          lineStyle: {
            width: 1,
            color: '#faad14' // 黄色
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

    // 使用 silent 模式更新图表，避免动画卡顿
    chartInstance.current.setOption(option, true);
    // 确保图表使用容器的完整高度
    chartInstance.current.resize();
  };

  // 获取股票 K 线数据
  const fetchKLineData = async (stockCode: string, days: number = 20, endDate: string = selectedDate) => {
    // 总是获取所有数据，用于支持完整的缩放功能
    const validDays = 9999; // 使用大值确保获取所有数据
    console.log('Fetching K line data for:', stockCode, 'days:', validDays, 'endDate:', endDate);
    setKLineLoading(true);
    try {
      const data = await getStockKLineData(stockCode, validDays, endDate);
      console.log('K line data received:', data);
      setKLineData(data);
      // 渲染图表由useEffect处理，这里不需要手动调用
    } catch (error) {
      console.error('Error fetching K line data:', error);
      message.error('获取 K 线数据失败');
    } finally {
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

  // K 线数据变化时更新图表
  useEffect(() => {
    if (Array.isArray(kLineData) && kLineData.length > 0) {
      const displayDays = timeRange === 'ALL' ? 365 : parseInt(timeRange);
      const startIndex = Math.max(0, kLineData.length - displayDays);
      const startPercent = (startIndex / kLineData.length) * 100;
      const endPercent = 100;
      renderKLineChart(kLineData, startPercent, endPercent);
    }
  }, [kLineData, timeRange]);

  // 日期变化处理
  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      setSelectedIndustry('');
      setAiApplied(false);
      fetchStocks(newDate, '');
      
      // 如果已经选择了股票，重新获取K线图数据，使用新的日期作为结束日期
      if (selectedStock) {
        fetchKLineData(selectedStock, parseInt(timeRange), newDate);
      }
    }
  };

  // 行业变化处理
  const handleIndustryChange = (value: string | null) => {
    setSelectedIndustry(value || '');
    fetchStocks(selectedDate, value || '', aiApplied ? aiStockCodes : undefined);
  };

  // 规则变化处理
  const handleRuleChange = (value: string | null) => {
    setSelectedRule(value || '');
    // 重新应用筛选
    let filtered = stocks;
    if (value) {
      filtered = filtered.filter((stock: any) => {
        if (!stock.triggered_rules) return false;
        return stock.triggered_rules.some((rule: any) => 
          (rule.rule_chinese_name || rule.rule_name) === value
        );
      });
    }
    // 应用股票名称模糊查询
    if (stockNameFilter) {
      const filterLower = stockNameFilter.toLowerCase();
      filtered = filtered.filter((stock: any) => 
        stock.stock_name && stock.stock_name.toLowerCase().includes(filterLower)
      );
    }
    setFilteredStocks(filtered);
  };

  // 股票名称过滤变化处理
  const handleStockNameFilterChange = (value: string) => {
    setStockNameFilter(value);
    // 重新应用筛选
    let filtered = stocks;
    if (selectedRule) {
      filtered = filtered.filter((stock: any) => {
        if (!stock.triggered_rules) return false;
        return stock.triggered_rules.some((rule: any) => 
          (rule.rule_chinese_name || rule.rule_name) === selectedRule
        );
      });
    }
    if (value) {
      const filterLower = value.toLowerCase();
      filtered = filtered.filter((stock: any) => 
        stock.stock_name && stock.stock_name.toLowerCase().includes(filterLower)
      );
    }
    setFilteredStocks(filtered);
  };

  // 清除AI分析结果
  const clearAiAnalysis = () => {
    setAiApplied(false);
    fetchStocks(selectedDate, selectedIndustry);
    message.success('已清除AI分析结果');
  };

  // 应用AI分析结果到查询
  const applyAiAnalysis = () => {
    if (aiStockCodes.length > 0) {
      console.log('应用AI分析结果，股票代码:', aiStockCodes);
      fetchStocks(selectedDate, selectedIndustry, aiStockCodes);
      setDrawerVisible(false);
      setAiApplied(true);
      message.success(`Apply ${aiStockCodes.length} opportunities`);
    } else {
      message.warning('请先进行AI分析获取股票代码');
    }
  };

  // 股票选择处理
  const handleStockSelect = (stockCode: string) => {
    console.log('Selected stock:', stockCode);
    setSelectedStock(stockCode);
    // 根据开关状态决定使用哪个日期作为K线图结束日期
    const kLineEndDate = showLatestDateKLine ? latestTradingDate : selectedDate;
    fetchKLineData(stockCode, parseInt(timeRange), kLineEndDate);
  };

  // 时间范围变化处理
  const handleTimeRangeChange = (value: string) => {
    setTimeRange(value);
    if (selectedStock) {
      // 根据开关状态决定使用哪个日期作为K线图结束日期
      const kLineEndDate = showLatestDateKLine ? latestTradingDate : selectedDate;
      fetchKLineData(selectedStock, parseInt(value), kLineEndDate);
    }
  };

  // 调用豆包API分析机会个股
  const analyzeOpportunityStocks = async () => {
    if (!aiInput.trim()) {
      message.warning('请输入分析内容');
      return;
    }
    
    setAiLoading(true);
    setAiResult('');
    
    try {
      // 直接传递用户输入内容
      const result = await analyzeOpportunityStocksAPI(aiInput);
      setAiResult(result.analysis);
      
      // 提取股票代码
      console.log('API返回结果:', result.analysis);
      
      // 尝试多种方式解析股票代码
      let stockCodes: string[] = [];
      
      // 方式1：匹配"机会个股：["开头的数组
      const stockCodeMatch = result.analysis.match(/机会个股：\s*\[(.*?)\]/s);
      if (stockCodeMatch) {
        try {
          const stockCodesStr = `[${stockCodeMatch[1]}]`;
          const parsedCodes = JSON.parse(stockCodesStr);
          if (Array.isArray(parsedCodes)) {
            stockCodes = parsedCodes;
          }
        } catch (e) {
          console.error('解析股票代码失败:', e);
        }
      }
      
      // 方式2：直接查找所有6位数字的股票代码
      if (stockCodes.length === 0) {
        const stockCodeRegex = /[0-9]{6}/g;
        const matchedCodes = result.analysis.match(stockCodeRegex) || [];
        stockCodes = matchedCodes;
      }
      
      // 方式3：匹配"opportunities"或"stocks"等英文关键词后的股票代码
      if (stockCodes.length === 0) {
        const enMatch = result.analysis.match(/(opportunities|stocks)[:：]\s*\[(.*?)\]/i);
        if (enMatch) {
          try {
            const stockCodesStr = `[${enMatch[2]}]`;
            const parsedCodes = JSON.parse(stockCodesStr);
            if (Array.isArray(parsedCodes)) {
              stockCodes = parsedCodes;
            }
          } catch (e) {
            console.error('解析英文格式股票代码失败:', e);
          }
        }
      }
      
      // 去重并过滤有效的股票代码
      stockCodes = [...new Set(stockCodes.filter(code => /^[0-9]{6}$/.test(code)))];
      
      if (stockCodes.length > 0) {
        setAiStockCodes(stockCodes);
        message.success(`Analysis Complete. ${stockCodes.length} opportunities identified.`);
      } else {
        message.error('未找到股票代码');
        setAiStockCodes([]);
      }
    } catch (error: any) {
      console.error('AI分析失败:', error);
      if (error.response && error.response.data && error.response.data.detail) {
        message.error(`AI分析失败: ${error.response.data.detail}`);
      } else {
        message.error('AI分析失败，请稍后重试');
      }
    } finally {
      setAiLoading(false);
    }
  };

  // 组件初始化时加载数据
  useEffect(() => {
    const loadLatestTradingDay = async () => {
      try {
        const result = await getLatestTradingDay();
        const latestDate = result.date;
        setLatestTradingDate(latestDate); // 保存最新交易日
        setSelectedDate(latestDate);
        fetchStocks(latestDate, '', aiApplied ? aiStockCodes : undefined);
      } catch (error) {
        message.error('获取最新交易日失败');
        // 如果获取最新交易日失败，使用当前日期
        fetchStocks(selectedDate, '', aiApplied ? aiStockCodes : undefined);
      }
    };
    loadLatestTradingDay();
  }, []);

  // 表格列定义
  const columns = [
    {
      title: 'Date',
      dataIndex: 'date',
      key: 'date',
      width: 100,
      align: 'center',
    },
    {
      title: 'Industry',
      dataIndex: 'industry',
      key: 'industry',
      width: 150,
      align: 'center',
      render: (text: any) => text || '未知',
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
      width: 100,
      align: 'center',
    },
    {
      title: 'Close',
      dataIndex: 'close',
      key: 'close',
      width: 100,
      align: 'right',
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
          <Text style={{ color: value >= 0 ? 'red' : 'green' }}>
            {value.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: 'U-days',
      dataIndex: 'growth_streak_days',
      key: 'growth_streak_days',
      width: 80,
      align: 'right',
      sorter: (a: any, b: any) => (a.growth_streak_days || 0) - (b.growth_streak_days || 0),
    },
    {
      title: 'U-pct',
      dataIndex: 'growth_streak_pct',
      key: 'growth_streak_pct',
      width: 100,
      align: 'right',
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
      title: 'Scan cnt',
      dataIndex: 'total_triggers',
      key: 'total_triggers',
      width: 80,
      align: 'right',
      sorter: (a: any, b: any) => (a.total_triggers || 0) - (b.total_triggers || 0),
      render: (text: any) => {
        const value = text || 0;
        return (
          <Text style={{ color: value > 0 ? 'red' : 'inherit' }}>
            {value}
          </Text>
        );
      },
    },
    {
      title: 'Scan rules',
      dataIndex: 'triggered_rules',
      key: 'triggered_rules',
      width: 100,
      maxWidth: 100,
      align: 'left',
      ellipsis: true,
      render: (rules: any[]) => {
        if (!rules || rules.length === 0) return '-';
        const ruleNames = rules.map(rule => rule.rule_chinese_name || rule.rule_name);
        const displayText = ruleNames.map(name => `【${name}】`).join(' ');
        return (
          <Tooltip title={displayText}>
            <span style={{ 
              display: 'block', 
              whiteSpace: 'nowrap', 
              overflow: 'hidden', 
              textOverflow: 'ellipsis'
            }}>
              {displayText}
            </span>
          </Tooltip>
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
          placeholder="Search by Industry"
          style={{ width: 200, marginRight: '12px' }}
          value={selectedIndustry}
          onChange={handleIndustryChange}
          allowClear
          showSearch
          optionFilterProp="children"
          filterOption={(input, option) =>
            (option?.children as unknown as string).toLowerCase().includes(input.toLowerCase())
          }
        >
          {industries.map(industry => (
            <Select.Option key={industry} value={industry}>{industry}</Select.Option>
          ))}
        </Select>
        <Select
          placeholder="Search by Rule"
          style={{ width: 200, marginRight: '12px' }}
          value={selectedRule}
          onChange={handleRuleChange}
          allowClear
          showSearch
          optionFilterProp="children"
          filterOption={(input, option) =>
            (option?.children as unknown as string).toLowerCase().includes(input.toLowerCase())
          }
        >
          {availableRules.map(rule => (
            <Select.Option key={rule} value={rule}>{rule}</Select.Option>
          ))}
        </Select>
         <Input
          placeholder="Search by Name"
          style={{ width: 200, marginRight: '12px' }}
          value={stockNameFilter}
          onChange={(e) => handleStockNameFilterChange(e.target.value)}
          allowClear
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
          type="primary"
          icon={<CalendarOutlined />}
          onClick={() => fetchStocks(selectedDate, selectedIndustry, aiApplied ? aiStockCodes : undefined)}
          loading={loading}
          style={{ marginRight: '12px' }}
        >
          查询
        </Button>
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
        <div style={{ flex: 6, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowX: 'auto' }}>
              <div style={{ minWidth: 600 }}>
                <Table
                  columns={columns}
                  dataSource={filteredStocks}
                  rowKey="stock_code"
                  loading={loading}
                  pagination={{ pageSize: 20 }}
                  size="small"
                  paginationPosition="bottom"
                  columnTitleProps={{
                    style: {
                      whiteSpace: 'nowrap',
                      textOverflow: 'ellipsis',
                      overflow: 'hidden'
                    }
                  }}
                />
              </div>
            </div>
          </Card>
        </div>

        {/* 右侧 K 线图 */}
        <div style={{ flex: 4, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, minWidth: 600, padding: 0, display: 'flex', flexDirection: 'column', minHeight: '600px' }} title={
            <Space>
              {selectedStock ? (
                <a 
                  href={(() => {
                    let market = '0'; // 默认深圳市场
                    if (selectedStock.startsWith('60') || selectedStock.startsWith('68')) {
                      market = '1'; // 上海市场
                    } else if (selectedStock.startsWith('00') || selectedStock.startsWith('30')) {
                      market = '0'; // 深圳市场
                    }
                    return `https://quote.eastmoney.com/basic/h5chart-iframe.html?code=${selectedStock}&market=${market}&type=r`;
                  })()} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  style={{ textDecoration: 'none', color: '#1890ff' }}
                >
                  {stockNames[selectedStock]} ({selectedStock})
                </a>
              ) : 'K 线图'}
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
                      const kLineEndDate = checked ? latestTradingDate : selectedDate;
                      fetchKLineData(selectedStock, parseInt(timeRange), kLineEndDate);
                    }
                  }}
                  checkedChildren="显示最新"
                  unCheckedChildren="查询日期"
                />
              </div>
            </Space>
          }>
            <div style={{ flex: 1, width: '100%', minHeight: '500px' }}>
              {selectedStock ? (
                <div style={{ width: '100%', height: '100%' }}>
                  {kLineLoading ? (
                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Text>加载中...</Text>
                    </div>
                  ) : (
                    <div ref={chartRef} style={{ width: '100%', height: '100%', minHeight: '400px' }} />
                  )}
                </div>
              ) : (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text>请选择一只股票查看 K 线图</Text>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* 股票详情弹窗 */}
      <Modal
        title={`${selectedStockData?.stock_name} (${selectedStockData?.stock_code}) 详情`}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={800}
      >
        {selectedStockData && (
          <div>
            <p><strong>行业:</strong> {selectedStockData.industry || '未知'}</p>
            <p><strong>日期:</strong> {selectedStockData.date}</p>
            <p><strong>收盘价:</strong> {selectedStockData.close?.toFixed(2) || '0.00'}</p>
            <p><strong>涨跌幅:</strong> <Text style={{ color: selectedStockData.change_rate >= 0 ? 'red' : 'green' }}>
              {selectedStockData.change_rate?.toFixed(2) || '0.00'}
            </Text></p>
            <p><strong>连涨天数:</strong> {selectedStockData.growth_streak_days || 0}</p>
            <p><strong>连涨幅度:</strong> {selectedStockData.growth_streak_pct?.toFixed(2) || '0.00'}</p>
            <p><strong>触发规则数:</strong> {selectedStockData.total_triggers || 0}</p>
            <p><strong>触发规则:</strong></p>
            <ul>
              {selectedStockData.triggered_rules?.map((rule: any, index: number) => (
                <li key={index}>{rule.rule_chinese_name || rule.rule_name}</li>
              )) || <li>无</li>}
            </ul>
          </div>
        )}
      </Modal>

      {/* AI分析抽屉 */}
      <Drawer
        title="Ask AI"
        placement="right"
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        size={500}
      >
        <div style={{ marginBottom: '20px' }}>
          <Input.TextArea
            placeholder="请输入分析内容，例如：新能源汽车行业政策利好"
            value={aiInput}
            onChange={(e) => setAiInput(e.target.value)}
            rows={6}
            style={{ marginBottom: '16px' }}
          />
          <Button
            type="primary"
            onClick={analyzeOpportunityStocks}
            loading={aiLoading}
            style={{ marginRight: '8px' }}
          >
            Ask
          </Button>
          <Button onClick={applyAiAnalysis} disabled={aiStockCodes.length === 0}>
            Apply
          </Button>
        </div>
        <div style={{ marginTop: '20px' }}>
          <Title level={5}>分析结果</Title>
          {aiLoading ? (
            <Text>分析中，请稍候...</Text>
          ) : aiResult ? (
            <div style={{ whiteSpace: 'pre-wrap', border: '1px solid #f0f0f0', padding: '12px', borderRadius: '4px' }}>
              {aiResult}
            </div>
          ) : (
            <Text>请输入分析内容并点击分析按钮</Text>
          )}
        </div>
      </Drawer>
    </div>
  );
};

export default StockList;