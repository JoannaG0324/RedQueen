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
export const getAnomalyStock = async (stockCode: string, targetDate: string, getRisk: boolean = false) => {
  const response = await api.get(`/anomaly/stock/${stockCode}`, {
    params: { target_date: targetDate, get_risk: getRisk }
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
  const params: any = { target_date: targetDate, industry: industry };
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

// 分析机会个股
export const analyzeOpportunityStocks = async (prompt: string) => {
  const response = await api.post('/ai/analyze', { prompt });
  return response.data;
};
