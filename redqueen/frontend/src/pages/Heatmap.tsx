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
  label?: {
    fontSize: number;
  };
  displayName?: string;
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

  /**
   * 根据涨跌幅(changePct)计算色块背景色
   * 配色规则：
   *   - 背景基色：深灰 rgb(20, 20, 22)，当 changePct→0 时接近暗色背景
   *   - 下跌（changePct < 0）：绿系，ratio 越大绿色越深
   *   - 上涨（changePct ≥ 0）：红系，ratio 越大红色越深
   *   - 比例计算：ratio = |changePct| / 0.2，即 ±20% 达到最大色阶，允许外推至 1.5 倍
   *
   * @param changePct 涨跌幅（1.23% 表示为 0.0123，-1.5% 表示为 -0.015）
   * @returns rgb(r, g, b) 字符串
   */
  const getColor = (changePct: number): string => {
    // 背景基色：近黑的深灰，当涨跌幅接近 0 时的底色
    const bgR = 20;
    const bgG = 20;
    const bgB = 22;

    if (changePct < 0) {
      // 下跌 → 绿色通道增量最大（bgG: 20→290），ratio: 0 → 1.5
      const absPct = Math.abs(changePct);
      const ratio = Math.min(absPct / 0.2, 1.5);

      const r = Math.round(bgR + ratio * 40);
      const g = Math.round(bgG + ratio * 180);
      const b = Math.round(bgB + ratio * 60);

      return `rgb(${r}, ${g}, ${b})`;
    } else {
      // 上涨 → 红色通道增量最大（bgR: 20→290），ratio: 0 → 1.5
      const ratio = Math.min(changePct / 0.2, 1.5);

      const r = Math.round(bgR + ratio * 180);
      const g = Math.round(bgG + ratio * 50);
      const b = Math.round(bgB + ratio * 60);

      return `rgb(${r}, ${g}, ${b})`;
    }
  };

  /**
   * 基于市值（亿元）预计算字号与显示文本
   * 这个函数用于 transformData 阶段给每个节点预绑一套 label 配置
   * （实际渲染时由 computeDynamicLabel 按 rect 重新计算，此处仅作为参考/fallback）
   *
   * 分级策略（按市值亿数）：
   *   <50 亿: 10px, 仅前 4 个字
   *   50~200 亿: 12px, 纯名称
   *   200~500 亿: 14px, 纯名称
   *   500~1000 亿: 16px, 名称 + 涨跌幅
   *   1000~3000 亿: 20px, 名称 + 涨跌幅
   *   ≥3000 亿: 26px, 名称 + 涨跌幅
   *
   * @param value 市值（单位：元）
   * @param name 原始名称（可能是 "名称\n+1.23%" 的多行格式）
   * @returns { fontSize, displayName } 字号与显示文本
   */
  const getLabelConfig = (value: number, name: string): { fontSize: number; displayName: string } => {
    const marketCapYi = value / 100000000; // 元转换为亿元
    const pureName = name.split('\n')[0];
    const changeText = name.split('\n')[1] || '';

    let fontSize: number;
    let displayName: string;

    if (marketCapYi < 50) {
      fontSize = 11;
      displayName = pureName.substring(0, 4);
    } else if (marketCapYi < 200) {
      fontSize = 12;
      displayName = pureName;
    } else if (marketCapYi < 500) {
      fontSize = 13;
      displayName = pureName;
    } else if (marketCapYi < 1000) {
      fontSize = 13;
      displayName = name;
    } else if (marketCapYi < 3000) {
      fontSize = 13;
      displayName = name;
    } else if (marketCapYi < 5000) {
      fontSize = 14;
      displayName = name;
    } else {
      fontSize = 20;
      displayName = name;
    }

    return { fontSize, displayName };
  };

  /**
   * 将后端返回的"扁平股票列表"转换为 ECharts treemap 所需的"两层树形结构"
   * 树结构：行业(父节点) → 股票(叶子节点)
   *
   * 数据转换过程：
   *   输入: [{ industry_code, industry_name, stock_code, stock_name, market_cap_r(市值, 元), change_pct(涨跌比例), industry_change_pct }, ...]
   *   输出: [{ name: 行业名, value: 行业总市值, children: [{ name: 股票名\n+X.XX%, value: 股票市值, changePct, itemStyle.color }, ...] }, ...]
   *
   * 关键点：
   *   - treemap 的面积由 value 决定，所以 value 必须是"市值"，单位是元
   *   - 颜色由 change_pct 决定，正涨红/负跌绿，比例越大颜色越深
   *   - 为了让 label 在 treemap 上显示多行文本（名称 + 涨跌幅），name 用 \n 拼接
   */
  const transformData = (stockData: StockData[]): TreemapData[] => {
    // 用 Map 按行业聚合，key=industry_code，value={行业名、子节点数组、总市值、行业涨跌幅}
    const industryMap = new Map<string, { name: string; children: TreemapData[]; totalValue: number; industryChangePct: number | null }>();

    stockData.forEach(stock => {
      // 过滤无效数据：市值为空/0 或 涨跌幅为空的股票直接跳过
      if (stock.market_cap_r === null || stock.market_cap_r <= 0 || stock.change_pct === null) {
        return;
      }

      // 首次遇到该行业：在 Map 中创建行业节点
      if (!industryMap.has(stock.industry_code)) {
        industryMap.set(stock.industry_code, {
          name: stock.industry_name,
          children: [],
          totalValue: 0,
          industryChangePct: stock.industry_change_pct
        });
      }

      const industry = industryMap.get(stock.industry_code)!;
      // 将涨跌比例(0.0123 表示 +1.23%)转为带 + / - 的百分比文本，拼到 name
      const changeStr = (stock.change_pct * 100).toFixed(1);
      const name = `${stock.stock_name}\n${stock.change_pct >= 0 ? '+' : ''}${changeStr}%`;
      // 基于市值预先计算一个字号和显示文本（供 levels 的 label 回调中使用，或作为 fallback）
      const labelConfig = getLabelConfig(stock.market_cap_r, name);
      industry.children.push({
        name,
        value: stock.market_cap_r,      // 决定该股票在 treemap 上的面积大小
        changePct: stock.change_pct,     // 供 tooltip 显示和颜色计算
        itemStyle: {
          color: getColor(stock.change_pct) // 涨跌颜色
        },
        label: {
          fontSize: labelConfig.fontSize // 基于市值的字号（levels 回调会用 rect 重新动态计算）
        },
        displayName: labelConfig.displayName // 基于市值的截断显示文本（预留字段）
      });
      industry.totalValue += stock.market_cap_r; // 累计行业总市值
    });

    // 将 Map 转为数组，每个行业成为一个父节点，children 是其下所有股票
    return Array.from(industryMap.values()).map(industry => {
      const industryLabelConfig = getLabelConfig(industry.totalValue, industry.name);
      return {
        name: industry.name,
        value: industry.totalValue,
        changePct: industry.industryChangePct ?? 0,
        children: industry.children,
        // 行业颜色：若有行业涨跌幅则按规则上色，否则不覆盖默认色
        itemStyle: industry.industryChangePct !== null ? {
          color: getColor(industry.industryChangePct)
        } : undefined,
        label: {
          fontSize: industryLabelConfig.fontSize
        },
        displayName: industryLabelConfig.displayName
      };
    });
  };

  const renderChart = useCallback((treemapData: TreemapData[]) => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    const containerRect = container.getBoundingClientRect();
    
    if (containerRect.width <= 0 || containerRect.height <= 0) {
      return;
    }

    /**
     * 根据色块实际渲染尺寸，动态计算字号与标签内容
     * 设计思路：
     *   1. 优先从 params.rect 获取真实渲染宽高（ECharts treemap 在 label formatter 回调中注入）
     *   2. 若 rect 不可用，则基于 value 相对于整棵树的最大值，按开方比例估算尺寸
     *   3. 字号 = min(宽, 高) * 0.30，范围限制在 8~28px，保证可读性与不溢出
     *   4. 内容 = 名称 + 换行 + 涨跌幅（若 hasChangePct=true 且存在涨跌幅文本）
     * 说明：
     *   之前版本根据 rect 做了"分级显示规则"（小色块只显示3个字、中等色块只显示名称等），
     *   但实际效果是只有大色块才显示文字，信息密度不足；
     *   当前策略改为——所有色块统一使用动态字号，统一显示完整内容，后续如需精细化控制再引入分级。
     */
    const computeDynamicLabel = (params: any, hasChangePct: boolean) => {
      // 当前节点原始数据，含自定义 label/displayName
      const data = params.data as TreemapData;
      // 节点显示文本：格式为 "名称\n+1.23%"，按 \n 拆分出纯名称与涨跌幅
      const rawName = data.name || params.name || '';
      const parts = rawName.split('\n');
      const pureName = parts[0] || '';
      const changeText = parts[1] || '';

      // === 第一步：获取色块实际渲染宽高 ===
      let w = 0;
      let h = 0;
      if (params.rect && (params.rect.width > 0 || params.rect.height > 0)) {
        // 优先使用 ECharts 注入的 rect（真实渲染尺寸）
        w = params.rect.width || 0;
        h = params.rect.height || 0;
      } else {
        // Fallback：当 rect 不可用时，基于 value 与根节点最大值的比例估算尺寸
        const value = params.value || data.value || 0;
        // 计算整棵树中所有节点 value 的最大值，用于归一化
        const maxVal = treemapData.reduce((m: number, d: TreemapData) => Math.max(m, d.value || 0), 0) || 1;
        // sqrt：面积是线性的，开方后让"小 value"的节点也能得到合理尺寸（不至于过小）
        const ratio = Math.sqrt(value / maxVal) * 120;
        w = Math.max(20, ratio);
        h = Math.max(20, ratio);
      }

      // === 第二步：基于最小边动态计算字号 ===
      // 取宽高中的较小者，保证在细长色块上字号也不会过大溢出
      const minSide = Math.min(w, h);
      // 字号公式：minSide * 0.30，并约束在 [8, 28] 区间
      //   - 小色块（minSide=30）→ 8~9px，刚好能显示 2~3 个中文
      //   - 中等色块（minSide=70）→ 21px，清晰可读
      //   - 大色块（minSide=120+）→ 28px，醒目
      let fontSize = Math.max(8, Math.min(28, Math.floor(minSide * 0.30)));

      // === 第三步：组装显示内容（统一策略：名称 + 可选涨跌幅，无分级隐藏） ===
      let content = '';

      // [注释保留 —— 原有分级显示规则，后续如需精细化可重新启用]
      // if (minSide < 22 || area < 400) { content = ''; }
      // else if (minSide < 40 || area < 1800) { content = pureName.substring(0, 3); }
      // else if (minSide < 70 || area < 6000) { content = pureName; }
      // else if (minSide < 110 || area < 18000) { content = pureName + '\n' + changeText; }
      // else { content = pureName + '\n' + changeText; }

      // 当前策略：所有色块都尝试显示完整名称 + 涨跌幅（有则显示）
      content = pureName;
      if (hasChangePct && changeText) {
        content = pureName + '\n' + changeText;
        // 多行显示时字号略小，防止垂直溢出
        fontSize = Math.max(9, fontSize - 1);
      }

      // lineHeight 与 fontSize 保持一致，确保单行文字垂直居中且多行间距合理
      const lineHeight = fontSize;

      return { fontSize, lineHeight, content };
    };

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
      /**
       * tooltip：鼠标 hover 时显示的提示框
       *   - trigger: 'item' —— 按"数据项"触发（点到哪个矩形显示哪个的信息）
       *   - formatter：自定义 HTML 内容，显示名称、市值、涨跌幅（按涨跌颜色着色）
       *   - 区分行业节点（有 children）和股票节点（叶子），股票节点额外显示市值
       */
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          // edge 类型是行业节点之间的分隔线，无需显示信息
          if (params.dataType === 'edge') {
            return '';
          }

          const data = params.data;
          const changePct = data.changePct;
          // 涨跌颜色：红涨绿跌（A股习惯）
          const changeColor = changePct !== undefined && changePct >= 0 ? '#ef232a' : '#11c26d';
          // 带符号的涨跌文本：如 "+3.21%"、"-1.50%"
          const changeText = changePct !== undefined ? `${(changePct >= 0 ? '+' : '')}${(changePct * 100).toFixed(2)}%` : '-';

          // 行业节点（父节点）：只显示行业名 + 涨跌幅
          if (data.children) {
            return `<div style="padding: 8px;">
              ${data.name}
              涨跌幅: <span style="color: ${changeColor}">${changeText}</span>
            </div>`;
          } else {
            // 股票节点（叶子）：显示股票名称 + 市值（亿元） + 涨跌幅
            return `<div style="padding: 8px;">
              <strong>${data.name.split('\\n')[0]}</strong><br/>
              市值: ${(data.value / 100000000).toFixed(2)} 亿<br/>
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
            left: 'center',
            bottom: 0,
            height: 25,
            separator: ' > ',
            textStyle: {
              fontSize: 16,
              color: '#4096ff'
            }
          },
          // 顶层全局 label 配置：全局默认样式（文字位置、颜色、字重），
          // 各层级（levels[i]）会覆盖或继承这里的配置
          // 注意：lineHeight / ellipsis 等属性不支持回调函数，在 levels 中通过 fontSize 间接控制
          label: {
            show: true,
            position: 'inside',
            align: 'center',
            verticalAlign: 'middle',
            distance: 0,
            color: '#fff',
            fontWeight: 'normal'
          },
          // 上层 label：当当前层级因空间不足无法显示标签时，退化为"缩略标签"
          upperLabel: {
            show: true,
            height: 20,
            fontSize: 14,
            fontWeight: 'bold',
            color: '#fff',
            emphasis: {
              color: '#000'
            }
          },
          itemStyle: {
            // borderColor: '#000000',
            // borderWidth: 0,
            // gapWidth: 0.5
          },
          /**
           * levels：层级化样式配置
           * 树结构一共三层，从根到叶子依次是：
           *   - levels[0]: 第一层（整棵树的虚拟根）→ 整体无边框，不显示标签
           *   - levels[1]: 第二层（行业父节点）→ 有行业分组样式，按矩形尺寸动态字号
           *   - levels[2]: 第三层（股票叶子节点）→ 每只股票的矩形，按矩形尺寸动态字号，label 显示"名称+涨跌幅"
           */
          levels: [
            {
              // levels[0]: 第一层（最外层容器）—— 不显示标签，无边框
              itemStyle: {
                borderWidth: 0,
                borderColor: 'transparent'
              },
              label: {
                show: false
              }
            },
            {
              // levels[1]: 第二级别（行业级）—— 行业色块分组
              //   - 显示行业名称（hasChangePct=false，不显示行业涨跌幅）
              //   - 字号由 computeDynamicLabel 按矩形尺寸动态计算
              //   - lineHeight 不设置回调（ECharts 默认 = fontSize，确保垂直居中）
              itemStyle: {
                borderColor: '#000000',
                borderWidth: 0,
                gapWidth: 0.7
              },
              label: {
                show: true,
                position: 'inside',
                align: 'center',
                verticalAlign: 'middle',
                distance: 0,
                // fontSize 回调：从 computeDynamicLabel 取按 rect 尺寸算得的字号
                fontSize: (params: any) => {
                  const info = computeDynamicLabel(params, false);
                  return info.fontSize;
                },
                // formatter 回调：从 computeDynamicLabel 取按 rect 尺寸算得的文本
                formatter: (params: any) => {
                  const info = computeDynamicLabel(params, false);
                  return info.content;
                }
              },
              emphasis: {
                itemStyle: {
                  borderColor: '#fff700ff',
                  borderWidth: 1
                }
              }
            },
            {
              // levels[2]: 第三级别（股票级，叶子节点）—— 每个股票的彩色矩形
              //   - 显示"股票名称 + 涨跌幅"（hasChangePct=true，显示第二行涨跌幅）
              //   - 字号由 computeDynamicLabel 按矩形尺寸动态计算
              //   - lineHeight 不设置回调（ECharts 默认 = fontSize，确保垂直居中）
              itemStyle: {
                borderColor: '#transparent',
                borderWidth: 0,
                gapWidth: 0.7
              },
              label: {
                show: true,
                position: 'inside',
                align: 'center',
                verticalAlign: 'middle',
                distance: 0,
                // fontSize 回调：股票矩形的尺寸决定字号，大面积股票字号大、小面积的小
                fontSize: (params: any) => {
                  const info = computeDynamicLabel(params, true);
                  return info.fontSize;
                },
                // formatter 回调：股票节点显示"名称\n+1.23%" 这种多行格式
                formatter: (params: any) => {
                  const info = computeDynamicLabel(params, true);
                  return info.content;
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