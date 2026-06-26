import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Card, Button, message, Tooltip, Drawer, Table, Typography, Spin } from 'antd';
import { CalendarOutlined, InfoCircleOutlined } from '@ant-design/icons';
import * as echarts from 'echarts';
import { getHeatmapData, getLatestTradingDay, getStockKLineData } from '../api/api';
import type { ColumnType } from 'antd/es/table';

const { Text } = Typography;

/**
 * K 线图数据结构
 */
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

/**
 * 配色刻度 bin（单个条段）数据结构
 */
interface ColorScaleBin {
  /** bin 的左边界（包含），例如 0.08 表示 >=8% */
  lower: number;
  /** bin 的右边界（不包含），例如 0.12 表示 <12% */
  upper: number;
  /** 该 bin 内包含的股票数量 */
  count: number;
  /** 占总数百分比，用于控制显示宽度：0~1 */
  percent: number;
  /** 段背景颜色（RGB 字符串） */
  color: string;
  /** 段标签：显示为右边界值（12%） */
  label: string;
  /** 段中点涨跌幅（取反用于颜色映射） */
  midpoint: number;
  /** 该段内包含的股票列表（点击时用于展示） */
  stocks: StockData[];
  /** 该段内所有股票的平均涨跌幅 */
  avgChangePct: number;
}

interface StockData {
  industry_code: string;
  industry_name: string;
  stock_code: string;
  stock_name: string;
  market_cap_r: number | null;
  period_pct: number | null;
  change_pct: number | null;
  industry_change_pct: number | null;
  close: number | null;
  turnover: number | null;
  volume_pct: number | null;
  growth_streak_days: number | null;
  growth_streak_pct: number | null;
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

  // 抽屉相关状态
  const [drawerVisible, setDrawerVisible] = useState<boolean>(false);
  const [selectedBin, setSelectedBin] = useState<ColorScaleBin | null>(null);

  // 抽屉内 K 线图相关状态
  const [selectedDrawerStock, setSelectedDrawerStock] = useState<string>('');
  const [drawerKLineData, setDrawerKLineData] = useState<KLineData[]>([]);
  const [drawerKLineLoading, setDrawerKLineLoading] = useState<boolean>(false);
  const drawerKLineChartRef = useRef<HTMLDivElement | null>(null);
  const drawerKLineChartInstance = useRef<echarts.ECharts | null>(null);

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
   * 计算指定排序数组的分位数（线性插值法）
   * @param sortedVals 已升序排序的数值数组
   * @param q 分位点，0~1，例如 0.5 = 中位数
   */
  const quantile = (sortedVals: number[], q: number): number => {
    if (sortedVals.length === 0) return 0;
    if (sortedVals.length === 1) return sortedVals[0];
    const pos = (sortedVals.length - 1) * q;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    if (idx + 1 >= sortedVals.length) return sortedVals[sortedVals.length - 1];
    return sortedVals[idx] + frac * (sortedVals[idx + 1] - sortedVals[idx]);
  };

  /**
   * 配色刻度段颜色：绿 → 白 → 红 平滑过渡
   *
   * 设计要点（相对于 getColor 的差异）：
   *   - 配色刻度显示在浅色（或白色）背景上，与 HeatMap（深色背景）不同
   *   - 因此采用：绿 → 白 → 红 的对称渐变（而非绿 → 深灰 → 红）
   *   - 取 |midpoint| / maxAbs 做归一化，避免极端值导致颜色过饱和
   *   - 白色 = "无色/中性"，对应 midpoint = 0
   *
   * @param midpoint 该刻度段中点的涨跌幅（小数，0.01 = 1%）
   * @param maxAbs 当前数据最大绝对值（用于归一化，避免极端值过饱和）
   * @returns rgb(r, g, b) 字符串
   */
  const getLegendColor = (midpoint: number, maxAbs: number): string => {
    // 归一化强度：0~1，clamp 上限为 0.3（即 30% 对应最深色）
    const t = maxAbs > 0 ? Math.min(Math.abs(midpoint) / Math.max(maxAbs, 0.005), 1) : 0;
    // 绿/红通道分别填充
    if (midpoint < 0) {
      // 下跌：白色 → 深绿
      //   r: 255 → 20,  g: 255 → 150, b: 255 → 40  （取更"亮绿"的偏绿）
      const r = Math.round(255 + t * (40 - 255));
      const g = Math.round(255 + t * (180 - 255));
      const b = Math.round(255 + t * (70 - 255));
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      // 上涨：白色 → 深红
      const r = Math.round(255 + t * (200 - 255));
      const g = Math.round(255 + t * (40 - 255));
      const b = Math.round(255 + t * (60 - 255));
      return `rgb(${r}, ${g}, ${b})`;
    }
  };

  /**
   * 基于个股涨跌幅计算 10 段配色刻度
   *
   * 算法说明（正负分区，共 10 段）：
   *   1. 取所有 stock.change_pct（已过滤 null），得到 [dataMin, dataMax]
   *   2. 将 [dataMin, 0] 做 **5 段均匀等分**（下跌刻度）
   *      将 [0, dataMax] 做 **5 段均匀等分**（上涨刻度）
   *      - 左闭右开：段 i = [ lower_i, upper_i )
   *      - 最后一段 = [ lower_9, upper_9 ]，闭右端（包含最大值）
   *      - 若 dataMin = 0（无下跌），则 [0, dataMax] 做 10 段均分
   *      - 若 dataMax = 0（无上涨），则 [dataMin, 0] 做 10 段均分
   *   3. 统计每段内股票数量 count_i
   *   4. 段**宽度** = count_i / total（体现"该涨跌区间聚集了多少只股票"，宽=密集）
   *   5. 段**颜色** = 基于段中点值 midpoint 做绿→白→红渐变（通过 getLegendColor）
   *   6. 段**标签** = 右边界值（例如 12%，表示该段覆盖 [x%, 12%)）
   *
   * 关键点：刻度边界以 0 为中心，左右对称分区；段宽度反映股票数密度。
   *
   * @param stockData 原始股票数据
   * @returns ColorScaleBin[]（固定 10 段）
   */
  const computeQuantileColorScale = (stockData: StockData[]): ColorScaleBin[] => {
    const NUM_BINS = 12;

    // 1) 提取有效区间涨跌幅（period_pct）
    const values: number[] = [];
    for (const s of stockData) {
      if (
        s.period_pct !== null &&
        s.period_pct !== undefined &&
        Number.isFinite(s.period_pct)
      ) {
        values.push(s.period_pct);
      }
    }

    // 空数据保护：返回 10 段灰色占位
    if (values.length === 0) {
      return Array.from({ length: NUM_BINS }, (_, i) => ({
        lower: i * 0.001,
        upper: (i + 1) * 0.001,
        count: 0,
        percent: 1 / NUM_BINS,
        color: 'rgb(240, 240, 240)',
        label: `${((i + 1) * 0.1).toFixed(1)}%`,
        midpoint: (i + 0.5) * 0.001,
        stocks: [],
        avgChangePct: 0
      }));
    }

    const total = values.length;
    const dataMin = Math.min.apply(null, values);
    const dataMax = Math.max.apply(null, values);
    const maxAbs = Math.max(Math.abs(dataMin), Math.abs(dataMax));
    const span = dataMax - dataMin;

    // 2) 以 0 为中心，分 [dataMin, 0] 和 [0, dataMax] 两个半区，共 NUM_BINS 段
    //    - 若 dataMin >= 0（无下跌股票），则整个区间 [0, dataMax] 均分 NUM_BINS 段
    //    - 若 dataMax <= 0（无上涨股票），则整个区间 [dataMin, 0] 均分 NUM_BINS 段
    //    - 若 dataMin == dataMax == 0（全持平），则人为扩展 ±0.01
    const boundaries: number[] = [];
    const NEG_BINS = Math.floor(NUM_BINS / 2);
    const POS_BINS = NUM_BINS - NEG_BINS;

    if (span === 0) {
      // 所有股票涨跌幅相同：人为扩展一个小区间以保证刻度可见
      const center = dataMin;
      const half = Math.max(Math.abs(center) * 0.05, 0.005);
      for (let i = 0; i <= NUM_BINS; i++) {
        boundaries.push(center - half + (2 * half * i) / NUM_BINS);
      }
    } else if (dataMin >= 0) {
      // 全为上涨或持平：[0, dataMax] 均分成 10 段
      for (let i = 0; i <= NUM_BINS; i++) {
        boundaries.push((dataMax * i) / NUM_BINS);
      }
    } else if (dataMax <= 0) {
      // 全为下跌或持平：[dataMin, 0] 均分成 10 段
      for (let i = 0; i <= NUM_BINS; i++) {
        boundaries.push(dataMin + ((0 - dataMin) * i) / NUM_BINS);
      }
    } else {
      // 有涨有跌：左半区 5 段 + 右半区 5 段
      // 左半区 5 段 [dataMin, 0]
      for (let i = 0; i <= NEG_BINS; i++) {
        boundaries.push(dataMin + ((0 - dataMin) * i) / NEG_BINS);
      }
      // 右半区 5 段 [0, dataMax]，注意跳过重复的 0 点
      for (let i = 1; i <= POS_BINS; i++) {
        boundaries.push((dataMax * i) / POS_BINS);
      }
    }

    // 3) 对每段统计落入 [lower, upper) 的股票数和股票列表（最后一段含最大值）
    const bins: ColorScaleBin[] = [];
    for (let i = 0; i < NUM_BINS; i++) {
      const lower = boundaries[i];
      const upper = i === NUM_BINS - 1 ? boundaries[i + 1] + 1e-9 : boundaries[i + 1];
      const isLastBin = i === NUM_BINS - 1;

      const stocks: StockData[] = [];
      for (const s of stockData) {
        const v = s.period_pct;
        if (v === null || v === undefined || !Number.isFinite(v)) continue;
        const EPSILON = 1e-9;
        if (v >= lower - EPSILON && (isLastBin ? v <= upper + EPSILON : v < upper + EPSILON)) {
          stocks.push(s);
        }
      }

      const count = stocks.length;
      const percent = total > 0 ? count / total : 1 / NUM_BINS;
      const midpoint = (lower + upper) / 2;
      const color = getLegendColor(midpoint, maxAbs);
      const labelPct = upper * 100;
      const label = `${labelPct.toFixed(0)}%`;

      // 计算该段内股票的平均区间涨跌幅
      const avgChangePct = count > 0
        ? stocks.reduce((sum, s) => sum + (s.period_pct || 0), 0) / count
        : 0;

      bins.push({ lower, upper, count, percent, color, label, midpoint, stocks, avgChangePct });
    }

    return bins;
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
      // 过滤无效数据：市值为空/0 或 区间涨跌幅为空的股票直接跳过
      if (stock.market_cap_r === null || stock.market_cap_r <= 0 || stock.period_pct === null) {
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
      // 将区间涨跌比例(0.0123 表示 +1.23%)转为带 + / - 的百分比文本，拼到 name
      const changeStr = (stock.period_pct * 100).toFixed(1);
      const name = `${stock.stock_name}\n${stock.period_pct >= 0 ? '+' : ''}${changeStr}%`;
      // 基于市值预先计算一个字号和显示文本（供 levels 的 label 回调中使用，或作为 fallback）
      const labelConfig = getLabelConfig(stock.market_cap_r, name);
      industry.children.push({
        name,
        value: stock.market_cap_r,      // 决定该股票在 treemap 上的面积大小
        changePct: stock.period_pct,    // 供 tooltip 显示和颜色计算（区间涨跌幅）
        itemStyle: {
          color: getColor(stock.period_pct) // 区间涨跌颜色
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

  /**
   * 配色刻度：基于当前 data 计算
   * - data 变更 → 自动重新计算
   * - 固定 10 段，分位数边界
   * - 段宽度反映该区间内股票数占比
   */
  const colorScaleBins = useMemo(() => computeQuantileColorScale(data), [data]);

  /**
   * Drawer K 线图渲染函数
   * 与 StockList 页面的 K 线图逻辑保持一致，简化了部分交互功能
   */
  const renderDrawerKLineChart = useCallback((kLineData: KLineData[]) => {
    if (!drawerKLineChartRef.current || !Array.isArray(kLineData) || kLineData.length === 0) {
      return;
    }

    const container = drawerKLineChartRef.current;
    const rect = container.getBoundingClientRect();

    // 确保 ECharts 实例初始化
    if (!drawerKLineChartInstance.current) {
      drawerKLineChartInstance.current = echarts.init(container);
    }

    // 确保容器有最小高度
    if (rect.height < 350) {
      container.style.minHeight = '350px';
    }

    drawerKLineChartInstance.current.resize();

    // 转换数据格式为 ECharts 需要的格式
    const convertedData = kLineData.map(item => [
      item.date,
      parseFloat(item.open as any) || 0,
      parseFloat(item.close as any) || 0,
      parseFloat(item.low as any) || 0,
      parseFloat(item.high as any) || 0
    ]);

    // 提取成交量数据
    const volumeData = kLineData.map(item => [
      item.date,
      item.volume ? parseFloat(item.volume as any) : 0
    ]);

    // 提取 MA 数据
    const ma5Data = kLineData.map(item => [
      item.date,
      item.ma5 !== null ? parseFloat(item.ma5 as any) : null
    ]);
    const ma10Data = kLineData.map(item => [
      item.date,
      item.ma10 !== null ? parseFloat(item.ma10 as any) : null
    ]);
    const ma20Data = kLineData.map(item => [
      item.date,
      item.ma20 !== null ? parseFloat(item.ma20 as any) : null
    ]);
    const ma60Data = kLineData.map(item => [
      item.date,
      item.ma60 !== null ? parseFloat(item.ma60 as any) : null
    ]);

    // 计算 20 日滚动高点（H60）
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

    const h60Data = computeRollingHigh(kLineData, 60);

    // 默认显示最近 90 天的数据（缩放）
    const totalDays = kLineData.length;
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

          const stockData = kLineData[dataIndex];
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
                 H60: ${h60Data[dataIndex] !== null ? h60Data[dataIndex]?.toFixed(2) : '-'}<br/>
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
          data: kLineData.map(item => item.date),
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
          data: kLineData.map(item => item.date),
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
            width: 0.8,
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
            width: 0.8,
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
            width: 0.8,
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
            width: 0.8,
            color: '#689EFF'
          },
          symbol: 'none'
        },
        {
          name: 'H60',
          type: 'line',
          data: h60Data,
          smooth: false,
          showSymbol: false,
          symbol: 'none',
          lineStyle: {
            width: 1,
            color: '#ef232a',
            type: 'dashed'
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
              const klineItem = convertedData[index];
              return klineItem[2] >= klineItem[1] ? '#ef232a' : '#11c26d';
            }
          }
        }
      ]
    };

    drawerKLineChartInstance.current.setOption(option);
    drawerKLineChartInstance.current.resize();
  }, []);

  /**
   * Drawer K 线图数据获取函数
   * 以数据最新日期（date2）作为 endDate 查询个股历史 K 线数据
   */
  const fetchDrawerKLineData = useCallback(async (stockCode: string) => {
    if (!stockCode || !date2) {
      return;
    }

    setDrawerKLineLoading(true);
    setDrawerKLineData([]);

    // 清空旧图表
    if (drawerKLineChartInstance.current) {
      drawerKLineChartInstance.current.clear();
    }

    try {
      // 获取所有可用数据（days=9999），以 date2 作为结束日期
      const kLineResult = await getStockKLineData(stockCode, 9999, date2);

      if (Array.isArray(kLineResult) && kLineResult.length > 0) {
        setDrawerKLineData(kLineResult);
      } else {
        // 兜底：如果指定 endDate 返回空，尝试不指定 endDate
        const fallback = await getStockKLineData(stockCode, 9999, '');
        if (Array.isArray(fallback) && fallback.length > 0) {
          setDrawerKLineData(fallback);
        }
      }
    } catch (error) {
      console.error('获取 Drawer K 线数据失败:', error);
      message.error('获取 K 线数据失败');
    } finally {
      setDrawerKLineLoading(false);
    }
  }, [date2]);

  // Drawer K 线图数据变化时重新渲染
  useEffect(() => {
    if (drawerKLineData.length > 0 && drawerKLineChartRef.current) {
      renderDrawerKLineChart(drawerKLineData);
    }
  }, [drawerKLineData, renderDrawerKLineChart]);

  // Drawer 关闭时清理 K 线图状态
  useEffect(() => {
    if (!drawerVisible) {
      setSelectedDrawerStock('');
      setDrawerKLineData([]);
      setDrawerKLineLoading(false);
      if (drawerKLineChartInstance.current) {
        drawerKLineChartInstance.current.clear();
        drawerKLineChartInstance.current.dispose();
        drawerKLineChartInstance.current = null;
      }
    }
  }, [drawerVisible]);

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

        {/*
         * 热力图配色刻度条：
         * - 固定 10 段，每段按分位数分配边界
         * - 段宽度 = 段内股票数 / 总数（体现该区间聚集度）
         * - 颜色：绿（跌）→ 白（中性） → 红（涨）
         * - 段标签显示其右边界值（如 12%），表示该段覆盖 [lower, 12%)
         */}
        {colorScaleBins.length > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              marginLeft: 12,
              flex: 1,
              minWidth: 280,
              maxWidth: 1000
            }}
          >
            {/*
             * 条段主体：10 段并排（flex 布局，每段宽度 = percent × 总长）
             * - 最小段宽：每段至少 2%，避免零股票段完全消失
             * - 规范化：加了最小宽度后若总和 > 100%，按比例重新分配，保证总宽不超过容器
             * - 总容器最大宽度 520px，避免在宽屏上过度拉伸
             */}
            <div
              style={{
                display: 'flex',
                width: '100%',
                maxWidth: 1000,
                height: 32,
                border: '1px solid #e8e8e8',
                borderRadius: 4,
                overflow: 'hidden',
                background: '#fff'
              }}
            >
              {(() => {
                // 最小段宽占比（%）
                const MIN_WIDTH_PCT = 5;
                // 先计算带最小宽度保护的原始宽度
                const rawWidths = colorScaleBins.map((bin) =>
                  Math.max(bin.percent * 100, MIN_WIDTH_PCT)
                );
                const rawTotal = rawWidths.reduce((a, b) => a + b, 0);
                // 若总和 > 100%，按比例收缩；否则保持原宽（右侧留白）
                const widths = rawTotal > 100
                  ? rawWidths.map((w) => (w / rawTotal) * 100)
                  : rawWidths;

                return colorScaleBins.map((bin, idx) => {
                  const widthPct = widths[idx];
                  const rangeText = `[${(bin.lower * 100).toFixed(2)}%, ${(bin.upper * 100).toFixed(2)}%)`;
                return (
                  <Tooltip
                    key={idx}
                    title={
                      <div style={{ lineHeight: 1.8 }}>
                        <div>
                          <strong>区间：</strong>
                          {rangeText}
                          {idx === colorScaleBins.length - 1 ? '（含最大值）' : ''}
                        </div>
                        <div>
                          <strong>股票数：</strong>
                          {bin.count} 只（占 {((bin.count / Math.max(data.length, 1)) * 100).toFixed(1)}%）
                        </div>
                        <div>
                          <strong>中点涨跌幅：</strong>
                          <span style={{ color: bin.midpoint >= 0 ? '#ef232a' : '#11c26d', fontWeight: 'bold' }}>
                            {bin.midpoint >= 0 ? '+' : ''}{(bin.midpoint * 100).toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    }
                  >
                    <div
                      style={{
                        width: `${widthPct}%`,
                        background: bin.color,
                        position: 'relative',
                        height: '100%',
                        borderLeft: idx === 0 ? 'none' : '1px solid rgba(255,255,255,0.6)',
                        cursor: 'pointer'
                      }}
                      onClick={() => {
                        setSelectedBin(bin);
                        setDrawerVisible(true);
                      }}
                    >
                      {/* 段内标签：仅当宽度足够时才显示右边界值（段宽 > 5% 才显示文字） */}
                      {widthPct > 0 && (
                        <div
                          style={{
                            position: 'absolute',
                            top: '50%',
                            left: 0,
                            right: 0,
                            transform: 'translateY(-50%)',
                            fontSize: 12,
                            color: '#000',
                            textAlign: 'center',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            padding: '0 2px',
                            fontWeight: 500
                          }}
                        >
                          {bin.label}
                        </div>
                      )}
                    </div>
                  </Tooltip>
                );
              });
            })()}
            </div>
          </div>
        )}
      </div>

      <div
        ref={chartContainerRef}
        style={{ flex: 1, minHeight: 'calc(100vh - 150px)', width: '100%', position: 'relative' }}
      />

      {/* 抽屉：展示刻度区间内的个股信息 */}
      <Drawer
        title={
          selectedBin ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 13, lineHeight: 1.5 }}>
              <span>
                <strong style={{ color: '#666', marginRight: 4 }}>区间</strong>
                <span style={{ fontWeight: 'bold' }}>
                  [{(selectedBin.lower * 100).toFixed(2)}%, {(selectedBin.upper * 100).toFixed(2)})
                </span>
              </span>
              <span>
                <strong style={{ color: '#666', marginRight: 4 }}>数量</strong>
                <span style={{ fontWeight: 'bold' }}>
                  {selectedBin.count}({(selectedBin.percent * 100).toFixed(1)}%)
                </span>
              </span>
              <span>
                <strong style={{ color: '#666', marginRight: 4 }}>中点涨跌幅</strong>
                <Text
                  style={{
                    color: selectedBin.midpoint >= 0 ? '#ef232a' : '#11c26d',
                    fontWeight: 'bold'
                  }}
                >
                  {selectedBin.midpoint >= 0 ? '+' : ''}
                  {(selectedBin.midpoint * 100).toFixed(2)}%
                </Text>
              </span>
              <span>
                <strong style={{ color: '#666', marginRight: 4 }}>平均涨跌幅</strong>
                <Text
                  style={{
                    color: selectedBin.avgChangePct >= 0 ? '#ef232a' : '#11c26d',
                    fontWeight: 'bold'
                  }}
                >
                  {selectedBin.avgChangePct >= 0 ? '+' : ''}
                  {(selectedBin.avgChangePct * 100).toFixed(2)}%
                </Text>
              </span>
            </div>
          ) : '刻度详情'
        }
        placement="right"
        closable={true}
        onClose={() => {
          setDrawerVisible(false);
          setSelectedBin(null);
        }}
        open={drawerVisible}
        width={1000}
      >
        {selectedBin && (
          <>
            {/* K 线图模块：点击股票列表中的个股时显示，放在列表上方 */}
            {selectedDrawerStock && (
              <div style={{ marginTop: -12, marginBottom: 12 }}>
                <div style={{
                  background: '#f5f5f5',
                  padding: '8px 12px',
                  borderRadius: 8,
                  marginBottom: 8,
                  fontSize: 12
                }}>
                  <span style={{ fontWeight: 'bold' }}>
                    {selectedDrawerStock} - {
                      selectedBin?.stocks.find(s => s.stock_code === selectedDrawerStock)?.stock_name || ''
                    }
                  </span>
                  <span style={{ marginLeft: 16, color: '#666',fontWeight: 'bold' }}>
                    数据日期 {date2}
                  </span>
                </div>
                <Spin spinning={drawerKLineLoading} tip="加载中...">
                  <div
                    ref={drawerKLineChartRef}
                    style={{
                      width: '100%',
                      height: 280,
                      minHeight: 280,
                      background: '#fff',
                      borderRadius: 8
                    }}
                  />
                </Spin>
              </div>
            )}

            {/* 个股列表：宽度不超过容器 */}
            <div style={{ width: '100%', overflow: 'hidden' }}>
              <Table
                size="small"
                dataSource={selectedBin.stocks}
                pagination={{
                  pageSize: 15,
                  showSizeChanger: true,
                  showTotal: (total) => `共 ${total} 只`
                }}
                scroll={{ x: 'max-content' }}
                rowClassName={(record: StockData) =>
                  record && record.stock_code === selectedDrawerStock ? 'ant-table-row-hover-selected' : ''
                }
                onRow={(record: StockData) => ({
                  onClick: () => {
                    if (record && record.stock_code) {
                      setSelectedDrawerStock(record.stock_code);
                      fetchDrawerKLineData(record.stock_code);
                    }
                  }
                })}
                columns={[
                  {
                    title: 'Code',
                    dataIndex: 'stock_code',
                    key: 'stock_code',
                    width: 80,
                    align: 'center',
                    sorter: (a: StockData, b: StockData) =>
                      (a.stock_code || '').localeCompare(b.stock_code || '')
                  },
                  {
                    title: 'Name',
                    dataIndex: 'stock_name',
                    key: 'stock_name',
                    width: 80,
                    align: 'center',
                    sorter: (a: StockData, b: StockData) =>
                      (a.stock_name || '').localeCompare(b.stock_name || '')
                  },
                  {
                    title: 'Industry',
                    dataIndex: 'industry_name',
                    key: 'industry_name',
                    width: 80,
                    align: 'center',
                    ellipsis: true,
                    render: (text: string) => text || '未知',
                    sorter: (a: StockData, b: StockData) =>
                      (a.industry_name || '').localeCompare(b.industry_name || '')
                  },
                  {
                    title: 'Close',
                    dataIndex: 'close',
                    key: 'close',
                    width: 80,
                    align: 'right',
                    render: (text: number) =>
                      typeof text === 'number' ? text.toFixed(2) : '0.00',
                    sorter: (a: StockData, b: StockData) =>
                      (a.close ?? -Infinity) - (b.close ?? -Infinity)
                  },
                  {
                    title: 'Chg%',
                    dataIndex: 'change_pct',
                    key: 'change_pct',
                    width: 80,
                    align: 'right',
                    render: (text: number) => {
                      const value = typeof text === 'number' ? text : parseFloat(text) || 0;
                      return (
                        <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d' }}>
                          {value >= 0 ? '+' : ''}
                          {value.toFixed(2)}
                        </Text>
                      );
                    },
                    sorter: (a: StockData, b: StockData) =>
                      (a.change_pct ?? -Infinity) - (b.change_pct ?? -Infinity)
                  },
                  {
                    title: 'Turnover%',
                    dataIndex: 'turnover',
                    key: 'turnover',
                    width: 90,
                    align: 'right',
                    render: (text: number) =>
                      typeof text === 'number' ? text.toFixed(2) : '-',
                    sorter: (a: StockData, b: StockData) =>
                      (a.turnover ?? -Infinity) - (b.turnover ?? -Infinity)
                  },
                  {
                    title: 'Volume%',
                    dataIndex: 'volume_pct',
                    key: 'volume_pct',
                    width: 90,
                    align: 'right',
                    render: (text: number) => {
                      const value = typeof text === 'number' ? text : parseFloat(text) || 0;
                      if (!Number.isFinite(value)) return '-';
                      return (
                        <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d' }}>
                          {value >= 0 ? '+' : ''}
                          {value.toFixed(2)}
                        </Text>
                      );
                    },
                    sorter: (a: StockData, b: StockData) => {
                      const av = Number.isFinite(a.volume_pct) ? (a.volume_pct as number) : -Infinity;
                      const bv = Number.isFinite(b.volume_pct) ? (b.volume_pct as number) : -Infinity;
                      return av - bv;
                    }
                  },
                  {
                    title: 'Days',
                    dataIndex: 'growth_streak_days',
                    key: 'growth_streak_days',
                    width: 60,
                    align: 'center',
                    render: (text: number) => (text || 0).toString(),
                    sorter: (a: StockData, b: StockData) =>
                      (a.growth_streak_days ?? -Infinity) - (b.growth_streak_days ?? -Infinity)
                  },
                  {
                    title: 'Days%',
                    dataIndex: 'growth_streak_pct',
                    key: 'growth_streak_pct',
                    width: 80,
                    align: 'right',
                    render: (text: number) => {
                      const value = typeof text === 'number' ? text : parseFloat(text) || 0;
                      if (!Number.isFinite(value)) return '-';
                      return (
                        <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d' }}>
                          {value >= 0 ? '+' : ''}
                          {value.toFixed(2)}
                        </Text>
                      );
                    },
                    sorter: (a: StockData, b: StockData) => {
                      const av = Number.isFinite(a.growth_streak_pct) ? (a.growth_streak_pct as number) : -Infinity;
                      const bv = Number.isFinite(b.growth_streak_pct) ? (b.growth_streak_pct as number) : -Infinity;
                      return av - bv;
                    }
                  },
                  {
                    title: 'Period%',
                    key: 'period_pct',
                    width: 80,
                    align: 'right',
                    render: (_: any, record: StockData) => {
                      const value = typeof record.period_pct === 'number' ? record.period_pct : 0;
                      if (!Number.isFinite(value)) return '-';
                      return (
                        <Text style={{ color: value >= 0 ? '#ef232a' : '#11c26d' }}>
                          {value >= 0 ? '+' : ''}
                          {(value * 100).toFixed(1)}
                        </Text>
                      );
                    },
                    sorter: (a: StockData, b: StockData) => {
                      const av = Number.isFinite(a.period_pct) ? (a.period_pct as number) : -Infinity;
                      const bv = Number.isFinite(b.period_pct) ? (b.period_pct as number) : -Infinity;
                      return av - bv;
                    }
                  }
                ]}
                rowKey="stock_code"
                rowClassName={(record: StockData) =>
                  record && record.stock_code === selectedDrawerStock ? 'ant-table-row-hover-selected' : ''
                }
                onRow={(record: StockData) => ({
                  onClick: () => {
                    if (record && record.stock_code) {
                      setSelectedDrawerStock(record.stock_code);
                      fetchDrawerKLineData(record.stock_code);
                    }
                  }
                })}
              />
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
};

export default Heatmap;