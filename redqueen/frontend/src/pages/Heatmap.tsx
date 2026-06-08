import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Button, message, Tooltip } from 'antd';
import { CalendarOutlined, InfoCircleOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { getHeatmapData, getLatestTradingDay } from '../api/api';

interface StockData {
  industry_code: string;
  industry_name: string;
  stock_code: string;
  stock_name: string;
  market_cap_r: number | null;
  change_pct: number | null;
  industry_change_pct: number | null;
}

interface TreemapData {
  name: string;
  value: number;
  changePct?: number;
  itemStyle?: {
    color: string;
  };
  children?: TreemapData[];
}

const Heatmap: React.FC = () => {
  const [date1, setDate1] = useState<string>('');
  const [date2, setDate2] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [data, setData] = useState<StockData[]>([]);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [chartInstance, setChartInstance] = useState<echarts.ECharts | null>(null);

  useEffect(() => {
    loadLatestTradingDay();
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (chartInstance && chartContainerRef.current) {
        const rect = chartContainerRef.current.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          chartInstance.resize();
        }
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartInstance) {
        chartInstance.dispose();
      }
    };
  }, [chartInstance]);

  const loadLatestTradingDay = async () => {
    try {
      const result = await getLatestTradingDay();
      const latestDate = result.date;
      const date1Obj = new Date(latestDate);
      date1Obj.setDate(date1Obj.getDate() - 1);
      setDate1(date1Obj.toISOString().split('T')[0]);
      setDate2(latestDate);
    } catch (error) {
      message.error('获取最新交易日失败');
      const today = new Date();
      const date1Obj = new Date(today);
      date1Obj.setDate(date1Obj.getDate() - 1);
      setDate1(date1Obj.toISOString().split('T')[0]);
      setDate2(today.toISOString().split('T')[0]);
    }
  };

  const getColor = (changePct: number): string => {
    if (changePct < -0.5) {
      const ratio = (changePct + 0.5) / (-0.5);
      return `rgb(${Math.round(0 + ratio * 34)}, ${Math.round(139 + ratio * -100)}, ${Math.round(139 + ratio * 116)})`;
    } else if (changePct < 0) {
      const ratio = changePct / (-0.5);
      return `rgb(${Math.round(34 + ratio * 21)}, ${Math.round(139 + ratio * -105)}, ${Math.round(34 + ratio * 105)})`;
    } else if (changePct < 0.5) {
      const ratio = changePct / 0.5;
      return `rgb(${Math.round(220 + ratio * 35)}, ${Math.round(20 + ratio * 20)}, ${Math.round(60 + ratio * -30)})`;
    } else {
      const ratio = Math.min((changePct - 0.5) / 0.5, 1);
      return `rgb(${Math.round(255 - ratio * 30)}, ${Math.round(40 + ratio * 180)}, ${Math.round(30 + ratio * 100)})`;
    }
  };

  const transformData = (stockData: StockData[]): TreemapData[] => {
    const industryMap = new Map<string, { name: string; children: TreemapData[]; totalValue: number; industryChangePct: number | null }>();

    stockData.forEach(stock => {
      if (stock.market_cap_r === null || stock.market_cap_r <= 0 || stock.change_pct === null) {
        return;
      }

      if (!industryMap.has(stock.industry_code)) {
        industryMap.set(stock.industry_code, {
          name: stock.industry_name,
          children: [],
          totalValue: 0,
          industryChangePct: stock.industry_change_pct
        });
      }

      const industry = industryMap.get(stock.industry_code)!;
      const changeStr = (stock.change_pct * 100).toFixed(1);
      industry.children.push({
        name: `${stock.stock_name}\n${stock.change_pct >= 0 ? '+' : ''}${changeStr}%`,
        value: stock.market_cap_r,
        changePct: stock.change_pct,
        itemStyle: {
          color: getColor(stock.change_pct)
        }
      });
      industry.totalValue += stock.market_cap_r;
    });

    return Array.from(industryMap.values()).map(industry => ({
      name: industry.name,
      value: industry.totalValue,
      changePct: industry.industryChangePct ?? 0,
      children: industry.children,
      itemStyle: industry.industryChangePct !== null ? {
        color: getColor(industry.industryChangePct)
      } : undefined
    }));
  };

  const renderChart = useCallback((treemapData: TreemapData[]) => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const rect = container.getBoundingClientRect();
    
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }

    let instance = chartInstance;
    if (!instance) {
      instance = echarts.init(container, undefined, {
        renderer: 'canvas',
        useDirtyRect: false
      });
      setChartInstance(instance);
    }

    instance.resize();

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.dataType === 'edge') {
            return '';
          }
          
          const data = params.data;
          const changePct = data.changePct;
          const changeColor = changePct !== undefined && changePct >= 0 ? '#ef232a' : '#11c26d';
          const changeText = changePct !== undefined ? `${(changePct >= 0 ? '+' : '')}${(changePct * 100).toFixed(2)}%` : '-';
          
          if (data.children) {
            return `<div style="padding: 8px;">
              ${data.name}
              涨跌幅: <span style="color: ${changeColor}">${changeText}</span>
            </div>`;
          } else {
            return `<div style="padding: 8px;">
              <strong>${data.name.split('\\n')[0]}</strong><br/>
              市值: ${(data.value / 10000).toFixed(2)} 亿<br/>
              涨跌幅: <span style="color: ${changeColor}">${changeText}</span>
            </div>`;
          }
        }
      },
      series: [
        {
          type: 'treemap',
          visibleMin: 80,
          top: 0, 
          bottom: 0,
          left: 0,
          right: 0,
          breadcrumb: {
            show: true,
            formatter: "View",  
            left: 'center',
            bottom: 0,
            height: 25,
            separator: ' > ',
            textStyle: {
              fontSize: 16,
              color: '#4096ff'
            }
          },
          label: {
            show: true,
            position: 'inside',
            fontSize: (params: any) => {
              const value = params.value;
              if (value < 100) return 6;
              if (value < 500) return 7;
              if (value < 1000) return 8;
              if (value < 5000) return 9;
              if (value < 10000) return 10;
              if (value < 50000) return 11;
              return 20;
            },
            color: '#ffffffff',
            fontWeight: 'bold',
            lineHeight: 14,
            formatter: (params: any) => {
              const value = params.value;
              const name = params.name;
              if (value < 100) {
                return name.split('\n')[0].substring(0, 4);
              }
              return name;
            }
          },
          upperLabel: {
            show: true,
            height: 20,
            fontSize: 12,
            fontWeight: 'bold'
          },
          itemStyle: {
            borderColor: '#ffffffff',
            borderWidth: 0.5,
            gapWidth: 0
          },
          levels: [
            {
              itemStyle: {
                borderWidth: 0,
                borderColor: 'transparent'
              },
              label: {
                show: false
              }
            },
            {
              itemStyle: {
                borderWidth: 1
              },
              label: {
                show: true,
                fontSize: 10,
                lineHeight: 14
              },
              emphasis: {
                itemStyle: {
                  borderColor: '#fff700ff',
                  borderWidth: 1
                }
              }
            }
          ],
          data: treemapData
        }
      ]
    };

    instance.setOption(option);
  }, [chartInstance]);

  useEffect(() => {
    if (data.length > 0) {
      const treemapData = transformData(data);
      renderChart(treemapData);
    }
  }, [data, renderChart]);

  useEffect(() => {
    if (date1 && date2) {
      fetchHeatmapData();
    }
  }, [date1, date2]);

  const fetchHeatmapData = async () => {
    if (!date1 || !date2) {
      return;
    }

    if (new Date(date1) >= new Date(date2)) {
      return;
    }

    setLoading(true);
    try {
      const result = await getHeatmapData(date1, date2);
      setData(result);
    } catch (error) {
      console.error('获取热力图数据失败:', error);
      message.error('获取热力图数据失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 'calc(100vh - 150px)' }}>
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CalendarOutlined style={{ fontSize: 16 }} />
          <span>起始日期:</span>
          <input
            type="date"
            value={date1}
            onChange={(e) => setDate1(e.target.value)}
            style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '32px' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>结束日期:</span>
          <input
            type="date"
            value={date2}
            onChange={(e) => setDate2(e.target.value)}
            style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '32px' }}
          />
        </div>
        <Button
          type="primary"
          onClick={fetchHeatmapData}
          loading={loading}
        >
          查询
        </Button>
      </div>

      <div
        ref={chartContainerRef}
        style={{ flex: 1, minHeight: 'calc(100vh - 150px)', width: '100%', position: 'relative' }}
      />
    </div>
  );
};

export default Heatmap;