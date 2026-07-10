import React, { useState, useEffect, useRef } from 'react';
import { Space, Table, Button, Card, Select, Input, Tooltip, message, Radio } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CalendarOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { getLatestTradingDay, getIndustryList, getIndustryKLineData } from '../api/api';

// 行业数据类型定义
interface IndustryData {
  industry: string;
  industry_code: string;
  count: number;
  up_pct: number;
  net_inflow: number;
  change_percent: number;
  dev_3: number;
  dev_5: number;
  dev_20: number;
  dev_60: number;
  growth_streak_days?: number;
  growth_streak_pct?: number;
  growth_streak_days_loose?: number;
}

// K线数据类型定义
interface KLineData {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  amount: number;
}

const Industry: React.FC = () => {
  // 状态管理
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [industries, setIndustries] = useState<IndustryData[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState<string | undefined>(undefined);
  const [selectedIndustryCode, setSelectedIndustryCode] = useState<string>('');
  const [timeRange, setTimeRange] = useState<string>('90');
  const [searchIndustry, setSearchIndustry] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [kLineData, setKLineData] = useState<KLineData[]>([]);
  const [sortConfig, setSortConfig] = useState<{ key: keyof IndustryData; direction: 'ascend' | 'descend' } | null>(null);
  
  // 图表引用
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // 组件挂载时初始化
  useEffect(() => {
    loadLatestTradingDay();
  }, []);

  // 加载最新交易日
  const loadLatestTradingDay = async () => {
    try {
      const result = await getLatestTradingDay();
      const latestDate = result.date;
      setSelectedDate(latestDate);
      fetchIndustryData(latestDate);
    } catch (error) {
      message.error('获取最新交易日失败');
      // 如果获取最新交易日失败，使用当前日期
      fetchIndustryData(selectedDate);
    }
  };

  // 获取行业数据
  const fetchIndustryData = async (date: string) => {
    setLoading(true);
    try {
      // 调用API获取行业数据
      const data = await getIndustryList(date);
      // 按Up Pct (%)从高到低排序
      const sortedData = [...data].sort((a, b) => b.up_pct - a.up_pct);
      setIndustries(sortedData);
      // 默认选择第一个行业
      if (sortedData.length > 0) {
        setSelectedIndustry(sortedData[0].industry);
        setSelectedIndustryCode(sortedData[0].industry_code);
        fetchKLineData(sortedData[0].industry_code, parseInt(timeRange), date);
      }
    } catch (error) {
      console.error('获取行业数据失败:', error);
      message.error('获取行业数据失败');
    } finally {
      setLoading(false);
    }
  };

  // 获取K线数据
  const fetchKLineData = async (industryCode: string, days: number, endDate: string) => {
    // 总是获取所有数据，用于支持完整的缩放功能
    const validDays = 9999; // 使用大值确保获取所有数据
    console.log('Fetching K line data for industry:', industryCode, 'days:', validDays, 'endDate:', endDate);
    try {
      // 调用API获取行业K线数据
      const data = await getIndustryKLineData(industryCode, validDays, endDate);
      console.log('API返回的K线数据:', data);
      setKLineData(data);
      // 根据选择的时间范围设置缩放范围
      if (data.length > 0) {
        const displayDays = days === 365 ? data.length : days;
        const startIndex = Math.max(0, data.length - displayDays);
        const startPercent = (startIndex / data.length) * 100;
        const endPercent = 100;
        renderKLineChart(data, startPercent, endPercent);
      }
    } catch (error) {
      console.error('获取K线数据失败:', error);
      message.error('获取K线数据失败');
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
  const renderKLineChart = (data: KLineData[], startPercent: number = 0, endPercent: number = 100) => {
    console.log('Rendering K line chart...');
    console.log('chartInstance.current:', chartInstance.current);
    console.log('kLineData.length:', data.length);
    console.log('Zoom range:', startPercent, '% to', endPercent, '%');
    
    // 确保 ECharts 实例已经初始化
    if (!chartInstance.current && chartRef.current) {
      chartInstance.current = echarts.init(chartRef.current);
      console.log('Chart instance created:', chartInstance.current);
    }
    
    if (!chartInstance.current || data.length === 0) return;

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
    console.log('Converted data:', convertedData);

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

    const periods = [20, 60, 120];
    const hlByPeriod: { [key: number]: { highs: any[]; lows: any[] } } = {};
    for (const period of periods) {
      const highs: any[] = [];
      const lows: any[] = [];
      for (let i = 0; i < data.length; i++) {
        if (i < period - 1) {
          highs.push([data[i].date, null]);
          lows.push([data[i].date, null]);
        } else {
          let h = -Infinity;
          let l = Infinity;
          for (let j = i - period + 1; j <= i; j++) {
            const hj = parseFloat(data[j].high as any);
            const lj = parseFloat(data[j].low as any);
            if (!isNaN(hj) && hj > h) h = hj;
            if (!isNaN(lj) && lj < l) l = lj;
          }
          highs.push([data[i].date, h]);
          lows.push([data[i].date, l]);
        }
      }
      hlByPeriod[period] = { highs, lows };
    }
    
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
            
            const h20Val = hlByPeriod[20].highs[dataIndex]?.[1];
            const h60Val = hlByPeriod[60].highs[dataIndex]?.[1];
            const h120Val = hlByPeriod[120].highs[dataIndex]?.[1];
            const l20Val = hlByPeriod[20].lows[dataIndex]?.[1];
            const h20Str = (typeof h20Val === 'number' && isFinite(h20Val)) ? h20Val.toFixed(2) : '-';
            const h60Str = (typeof h60Val === 'number' && isFinite(h60Val)) ? h60Val.toFixed(2) : '-';
            const h120Str = (typeof h120Val === 'number' && isFinite(h120Val)) ? h120Val.toFixed(2) : '-';
            const l20Str = (typeof l20Val === 'number' && isFinite(l20Val)) ? l20Val.toFixed(2) : '-';

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
                   H20: <span style="color: #ef232a">${h20Str}</span><br/>
                   H60: <span style="color: #ef232a">${h60Str}</span><br/>
                   H120: <span style="color: #ef232a">${h120Str}</span><br/>
                   L20: <span style="color: #11c26d">${l20Str}</span><br/>
                   成交量: ${volume}<br/>
                   成交额: ${amount}`;
          }
        },
      legend: {
        data: ['K 线', 'MA5', 'MA10', 'MA20', 'MA60', 'H20', 'H60', 'H120', 'L20', '成交量'],
        top: 5,
        left: 80,
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
          bottom: -5,
          zoomLock: false
        }
      ],
      grid: [
        {
          left: 80,
          right: 40,
          top: 45,
          bottom: '35%',
          containLabel: false
        },
        {
          left: 80,
          right: 40,
          top: '65%',
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
            show: false
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
            show: true,
            color: '#333',
            fontSize: 11,
            align: 'center'
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
          name: 'H20',
          type: 'line',
          data: hlByPeriod[20].highs,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            width: 1,
            type: 'dashed',
            color: '#ff4d4f'
          }
        },
        {
          name: 'H60',
          type: 'line',
          data: hlByPeriod[60].highs,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            width: 1,
            type: 'dashed',
            color: '#ef232a'
          }
        },
        {
          name: 'H120',
          type: 'line',
          data: hlByPeriod[120].highs,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            width: 1,
            type: 'dashed',
            color: '#9d0208'
          }
        },
        {
          name: 'L20',
          type: 'line',
          data: hlByPeriod[20].lows,
          smooth: false,
          symbol: 'none',
          lineStyle: {
            width: 1,
            type: 'dashed',
            color: '#b7ebc7'
          }
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
    // 确保图表使用容器的完整高度
    chartInstance.current.resize();
  };

  // 日期变化处理
  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      fetchIndustryData(newDate);
    }
  };

  // 行业选择处理
  const handleIndustrySelect = (record: IndustryData) => {
    setSelectedIndustry(record.industry);
    setSelectedIndustryCode(record.industry_code);
    fetchKLineData(record.industry_code, parseInt(timeRange), selectedDate);
  };

  // 时间范围变化处理
  const handleTimeRangeChange = (value: string) => {
    setTimeRange(value);
    if (selectedIndustryCode) {
      fetchKLineData(selectedIndustryCode, value === 'ALL' ? 365 : parseInt(value), selectedDate);
    }
  };

  // 排序处理
  const handleSort = (key: keyof IndustryData) => {
    let direction: 'ascend' | 'descend' = 'ascend';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascend') {
      direction = 'descend';
    }
    setSortConfig({ key, direction });
  };

  // 搜索过滤后的数据
  const filteredIndustries = searchIndustry 
    ? industries.filter(item => 
        item.industry.toLowerCase().includes(searchIndustry.toLowerCase())
      )
    : industries;

  // 排序后的数据
  const sortedIndustries = [...filteredIndustries].sort((a, b) => {
    if (!sortConfig) return 0;
    const aValue = a[sortConfig.key];
    const bValue = b[sortConfig.key];
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

  // 表格列定义
  const columns: ColumnsType<IndustryData> = [
    {
      title: 'Industry',
      dataIndex: 'industry',
      key: 'industry',
      width: 120,
      sorter: (a, b) => a.industry.localeCompare(b.industry),
      sortOrder: sortConfig && sortConfig.key === 'industry' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('industry')
      })
    },
    {
      title: 'Count',
      dataIndex: 'count',
      key: 'count',
      width: 80,
      align: 'right',
      sorter: (a, b) => a.count - b.count,
      sortOrder: sortConfig && sortConfig.key === 'count' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('count')
      })
    },
    {
      title: 'Up Pct (%)',
      dataIndex: 'up_pct',
      key: 'up_pct',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.up_pct - b.up_pct,
      sortOrder: sortConfig && sortConfig.key === 'up_pct' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('up_pct')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 55) ? '#ef232a' : '' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Net Inflow (亿)',
      dataIndex: 'net_inflow',
      key: 'net_inflow',
      width: 120,
      align: 'right',
      sorter: (a, b) => a.net_inflow - b.net_inflow,
      sortOrder: sortConfig && sortConfig.key === 'net_inflow' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('net_inflow')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Change (%)',
      dataIndex: 'change_percent',
      key: 'change_percent',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.change_percent - b.change_percent,
      sortOrder: sortConfig && sortConfig.key === 'change_percent' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('change_percent')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Dev 3 (%)',
      dataIndex: 'dev_3',
      key: 'dev_3',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.dev_3 - b.dev_3,
      sortOrder: sortConfig && sortConfig.key === 'dev_3' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('dev_3')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Dev 5 (%)',
      dataIndex: 'dev_5',
      key: 'dev_5',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.dev_5 - b.dev_5,
      sortOrder: sortConfig && sortConfig.key === 'dev_5' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('dev_5')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Dev 20 (%)',
      dataIndex: 'dev_20',
      key: 'dev_20',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.dev_20 - b.dev_20,
      sortOrder: sortConfig && sortConfig.key === 'dev_20' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('dev_20')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '0.00'}
        </span>
      )
    },
    {
      title: 'Dev 60 (%)',
      dataIndex: 'dev_60',
      key: 'dev_60',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.dev_60 - b.dev_60,
      sortOrder: sortConfig && sortConfig.key === 'dev_60' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('dev_60')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
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
      sortOrder: sortConfig && sortConfig.key === 'growth_streak_days' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('growth_streak_days')
      }),
      render: (text: number) => (
        <span>
          {typeof text === 'number' ? text.toFixed(1) : '-'}
        </span>
      )
    },
    {
      title: 'Days%',
      dataIndex: 'growth_streak_pct',
      key: 'growth_streak_pct',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.growth_streak_pct || 0) - (b.growth_streak_pct || 0),
      sortOrder: sortConfig && sortConfig.key === 'growth_streak_pct' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('growth_streak_pct')
      }),
      render: (text: number) => (
        <span style={{ color: (typeof text === 'number' && text >= 0) ? '#ef232a' : '#14b143' }}>
          {typeof text === 'number' ? text.toFixed(2) : '-'}
        </span>
      )
    },
    {
      title: 'Days_L',
      dataIndex: 'growth_streak_days_loose',
      key: 'growth_streak_days_loose',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.growth_streak_days_loose || 0) - (b.growth_streak_days_loose || 0),
      sortOrder: sortConfig && sortConfig.key === 'growth_streak_days_loose' ? sortConfig.direction : false,
      onHeaderCell: (column) => ({
        onClick: () => handleSort('growth_streak_days_loose')
      }),
      render: (text: number) => (
        <span>
          {typeof text === 'number' ? text.toFixed(1) : '-'}
        </span>
      )
    }
  ];

  // 键盘导航
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        e.preventDefault();
        const currentIndex = industries.findIndex(item => item.industry === selectedIndustry);
        let newIndex = currentIndex;
        if (e.key === 'ArrowUp') {
          newIndex = currentIndex > 0 ? currentIndex - 1 : industries.length - 1;
        } else {
          newIndex = currentIndex < industries.length - 1 ? currentIndex + 1 : 0;
        }
        if (industries[newIndex]) {
          handleIndustrySelect(industries[newIndex]);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [industries, selectedIndustry]);

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

  // K 线数据变化时更新图表
  useEffect(() => {
    if (kLineData.length > 0) {
      const displayDays = timeRange === 'ALL' ? 365 : parseInt(timeRange);
      const startIndex = Math.max(0, kLineData.length - displayDays);
      const startPercent = (startIndex / kLineData.length) * 100;
      const endPercent = 100;
      renderKLineChart(kLineData, startPercent, endPercent);
    }
  }, [kLineData, timeRange]);

  // 窗口大小变化时重新渲染图表
  useEffect(() => {
    const handleResize = () => {
      chartInstance.current?.resize();
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: '800px' }}>
      <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => handleDateChange(e.target.value)}
          style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '32px', marginRight: '12px' }}
        />
        <Input
          placeholder="Search by Industry"
          style={{ width: 200, marginRight: '12px' }}
          value={searchIndustry}
          onChange={(e) => setSearchIndustry(e.target.value)}
          allowClear
        />
        <Button
          type="primary"
          icon={<CalendarOutlined />}
          onClick={() => fetchIndustryData(selectedDate)}
          loading={loading}
          style={{ marginRight: '12px' }}
        >
          查询
        </Button>
      </div>

      <div style={{ width: '100%', flex: 1, display: 'flex', gap: 12, overflowX: 'hidden' }}>
        {/* 左侧行业列表 */}
        <div style={{ flex: 6, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Card style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, overflowX: 'auto' }}>
              <div style={{ minWidth: 600 }}>
                <Table
                  columns={columns}
                  dataSource={sortedIndustries}
                  rowKey="industry_code"
                  onRow={(record) => ({
                    onClick: () => handleIndustrySelect(record),
                    style: {
                      cursor: 'pointer',
                      backgroundColor: selectedIndustry === record.industry ? '#f0f7ff' : ''
                    }
                  })}
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
              {selectedIndustry} 
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
            </Space>
          }>
            <div 
              ref={chartRef} 
              style={{ flex: 1, minHeight: 400, width: '100%' }}
            />
          </Card>
        </div>
      </div>
    </div>
  );
};

export default Industry;