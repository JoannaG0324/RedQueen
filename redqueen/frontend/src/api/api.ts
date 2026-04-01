import axios from 'axios';

// 创建axios实例
const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 触发扫描
export const triggerScan = async () => {
  const response = await api.post('/scan/trigger');
  return response.data;
};

// 获取扫描状态
export const getScanStatus = async (taskId: string) => {
  const response = await api.get(`/scan/status/${taskId}`);
  return response.data;
};

// 获取异动个股列表
export const getAnomalyStocks = async (scanDate: string) => {
  const response = await api.get('/anomaly/stocks', {
    params: { scan_date: scanDate }
  });
  return response.data;
};

// 获取异动个股详情
export const getAnomalyStock = async (stockCode: string, scanDate: string) => {
  const response = await api.get(`/anomaly/stock/${stockCode}`, {
    params: { scan_date: scanDate }
  });
  return response.data;
};

// 导出异动个股清单
export const exportAnomalyStocks = async (scanDate: string) => {
  const response = await api.get('/anomaly/export', {
    params: { scan_date: scanDate },
    responseType: 'blob'
  });
  return response.data;
};

// 健康检查
export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};
