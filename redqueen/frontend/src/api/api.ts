import axios from 'axios';

// 创建axios实例
export const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 0, // 不设置超时时间
  headers: {
    'Content-Type': 'application/json'
  }
});

// 触发扫描
export const triggerScan = async (targetDate?: string) => {
  const response = await api.post('/scan/trigger', {}, {
    params: { target_date: targetDate }
  });
  return response.data;
};

// 获取扫描状态
export const getScanStatus = async (taskId: string) => {
  const response = await api.get(`/scan/status/${taskId}`);
  return response.data;
};

// 获取异动个股列表
export const getAnomalyStocks = async (targetDate: string) => {
  const response = await api.get('/anomaly/stocks', {
    params: { target_date: targetDate }
  });
  return response.data;
};

// 获取行业列表数据
export const getIndustryList = async (targetDate: string) => {
  const response = await api.get('/industry/list', {
    params: { target_date: targetDate }
  });
  return response.data;
};

// 获取行业 K 线数据
export const getIndustryKLineData = async (industryCode: string, days: number = 20, endDate: string = '') => {
  const params: any = { days: days };
  if (endDate) {
    params.end_date = endDate;
  }
  const response = await api.get(`/industry/kline/${industryCode}`, {
    params: params
  });
  return response.data;
};

// 获取异动个股详情
export const getAnomalyStock = async (stockCode: string, targetDate: string) => {
  const response = await api.get(`/anomaly/stock/${stockCode}`, {
    params: { target_date: targetDate }
  });
  return response.data;
};

// 导出异动个股清单
export const exportAnomalyStocks = async (targetDate: string) => {
  const response = await api.get('/anomaly/export', {
    params: { target_date: targetDate },
    responseType: 'blob'
  });
  return response.data;
};

// 健康检查
export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

// 获取股票列表
export const getStockList = async (targetDate: string, industry: string = '', stockCodes: string[] = []) => {
  const params: any = {};
  // 只有显式传了日期才往后端传 target_date；为空时让后端 fallback 到数据库中的最新交易日
  if (targetDate) {
    params.target_date = targetDate;
  }
  if (industry) {
    params.industry = industry;
  }
  if (stockCodes && stockCodes.length > 0) {
    params.stock_codes = stockCodes.join(',');
  }
  const response = await api.get('/stock/list', {
    params: params
  });
  return response.data;
};

// 获取股票 K 线数据
export const getStockKLineData = async (stockCode: string, days: number = 20, endDate: string = '') => {
  const params: any = { days: days };
  if (endDate) {
    params.end_date = endDate;
  }
  const response = await api.get(`/stock/kline/${stockCode}`, {
    params: params
  });
  return response.data;
};

// 获取最新的交易日
export const getLatestTradingDay = async () => {
  const response = await api.get('/stock/latest-trading-day');
  return response.data;
};

// 分析机会个股（支持指定Skill）
export const analyzeOpportunityStocks = async (prompt: string, skillName: string = 'opportunity_analysis') => {
  const response = await api.post('/ai/analyze', { prompt, skill_name: skillName });
  return response.data;
};

// 获取所有Skill列表
export const getSkills = async () => {
  const response = await api.get('/ai/skills');
  return response.data;
};

// 获取热力图数据
export const getHeatmapData = async (date1: string, date2: string) => {
  const response = await api.get('/heatmap/data', {
    params: { date1, date2 }
  });
  return response.data;
};

// 股票收藏相关接口
export interface FavoriteItem {
  stock_code: string;
  price_date: string | null;
  status: number;
  updated_time: string | null;
}

export const getFavoriteList = async (): Promise<FavoriteItem[]> => {
  const response = await api.get('/stock/favorites');
  return response.data;
};

export const getFavoriteOne = async (stockCode: string): Promise<FavoriteItem> => {
  const response = await api.get(`/stock/favorite/${stockCode}`);
  return response.data;
};

/** 更新收藏状态：status=1 收藏，status=0 取消收藏 */
export const upsertFavorite = async (
  stockCode: string,
  payload: { price_date?: string; status: number; tag?: string | null }
): Promise<FavoriteItem & { action?: string }> => {
  const response = await api.post(`/stock/favorite/${stockCode}`, payload);
  return response.data;
};

export const deleteFavorite = async (stockCode: string) => {
  const response = await api.delete(`/stock/favorite/${stockCode}`);
  return response.data;
};

export interface SectorInfo {
  code: string;
  name: string;
  change_rate: string;
}

export const getStockSectors = async (stockCode: string): Promise<{ sectors: SectorInfo[] }> => {
  const response = await api.get(`/stock/sector/${stockCode}`);
  return response.data;
};

export interface ConceptPlateData {
  concept_name: string;
  concept_id: string;
  date: string;
  stock_count: number;
  total_volume: number | null;
  avg_change_ratio: number;
  chg_1: number | null;
  chg_2: number | null;
  chg_3: number | null;
  chg_4: number | null;
  chg_5: number | null;
}

export const getSectorList = async (targetDate: string = ''): Promise<ConceptPlateData[]> => {
  const params: any = {};
  if (targetDate) {
    params.target_date = targetDate;
  }
  const response = await api.get('/sector/list', { params });
  return response.data;
};

export interface SectorStockData {
  stock_code: string;
  stock_name: string;
  close: number;
  change_pct: number;
  turnover: number;
  volume: number;
  amount: number;
  growth_streak_days: number | null;
  growth_streak_pct: number | null;
  volume_pct: number | null;
  high_20d: number | null;
  high_20d_last: number | null;
  high_120d_last: number | null;
}

export interface SectorStockResult {
  data: SectorStockData[];
  has_local_data: boolean;
  latest_fetch_time: string | null;
}

export const getSectorStocks = async (conceptId: string, conceptName: string, date: string = ''): Promise<SectorStockResult> => {
  const params: any = {
    concept_id: conceptId,
    concept_name: conceptName
  };
  if (date) {
    params.date = date;
  }
  const response = await api.get('/sector/stocks', { params });
  return response.data;
};

export interface UpdateSectorStocksResult {
  success: boolean;
  updated_count: number;
  message: string;
}

export const updateSectorStocks = async (conceptId: string, conceptName: string): Promise<UpdateSectorStocksResult> => {
  const response = await api.post('/sector/stocks/update', null, {
    params: {
      concept_id: conceptId,
      concept_name: conceptName
    }
  });
  return response.data;
};
