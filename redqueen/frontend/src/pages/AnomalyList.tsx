import React, { useState, useEffect } from 'react';
import { Button, Table, message, Space, Typography, Progress, Modal, Descriptions, Spin, Select, Input, Tooltip } from 'antd';
import { ReloadOutlined, ExportOutlined, LoadingOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { triggerScan, getScanStatus, getAnomalyStocks, exportAnomalyStocks, getAnomalyStock } from '../api/api';

const { Title, Text } = Typography;

interface AnomalyStock {
  id: number;
  stock_code: string;
  stock_name: string;
  scan_date: string;
  total_triggers: number;
  triggered_rules: Array<{ rule_name: string; rule_chinese_name: string; details: any }>;
  industry: string;
  industry_code: string;
  created_at: string;
}

// 规则详情映射
const ruleDetails: Record<string, string> = {
  'rule_ma_crossover': '均线交叉趋势异动 - MA5上穿MA20，量能确认，连续2日收盘价大于MA20',
  'rule_trendline_breakout': '趋势线突破异动 - 突破幅度1%，连续2日不跌破趋势线',
  'rule_dow_theory': '道氏高低点趋势异动 - 更高低点和更高高点',
  'rule_macd_divergence': 'MACD趋势背离异动 - 价格创新低，但DIF未创新低，金叉信号',
  'rule_bollinger_band_breakout': '布林带通道突破异动 - 带宽收敛，向上突破，持续2日',
  'rule_quantile_regression': '分位数回归趋势异动 - 斜率由负变正',
  'rule_volume_price_divergence': '量价背离趋势异动 - 价格创新低，成交量未创新低，3日内收阳',
  'rule_obv_trend': 'OBV能量潮趋势异动 - OBV创新高，价格未创新高，OBV上穿OBV均线',
  'rule_capital_flow': '主力资金流趋势异动 - 5日累计净流入占比≥5%，连续3日资金为正',
  'rule_turnover_trend': '换手率趋势异动 - 当日换手率≥2倍均值，股价处于相对低位，当日收涨，持续2日',
  'rule_atr_volatility': 'ATR波动率异动 - ATR从10%历史分位上升幅度≥50%，3日内收盘价持续上行',
  'rule_volatility_expansion': '波动率收敛-发散异动 - 波动率降至历史20%分位并持续10日',
  'rule_amplitude_trend': '振幅异动趋势识别 - 振幅异常增大'
};

const AnomalyList: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<any>(null);
  const [stocks, setStocks] = useState<AnomalyStock[]>([]);
  const [filteredStocks, setFilteredStocks] = useState<AnomalyStock[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [progressModalVisible, setProgressModalVisible] = useState(false);
  const [stockDetailModalVisible, setStockDetailModalVisible] = useState(false);
  const [selectedStock, setSelectedStock] = useState<any>(null);
  const [stockDetailLoading, setStockDetailLoading] = useState(false);
  const [industryRiskLoading, setIndustryRiskLoading] = useState(false);
  const [selectedIndustry, setSelectedIndustry] = useState<string>('');
  const [selectedRules, setSelectedRules] = useState<string[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [rules, setRules] = useState<Array<{ label: string; value: string }>>([]);

  // 触发扫描
  const handleTriggerScan = async () => {
    setScanLoading(true);
    try {
      const result = await triggerScan(selectedDate);
      setTaskId(result.task_id);
      setProgressModalVisible(true);
      message.success('扫描任务已启动');
    } catch (error: any) {
      if (error.response && error.response.status === 400) {
        message.error(error.response.data.detail || '非交易日');
      } else {
        message.error('启动扫描任务失败');
      }
    } finally {
      setScanLoading(false);
    }
  };

  // 轮询扫描状态
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const status = await getScanStatus(taskId);
          setScanStatus(status);
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(interval);
            setTaskId(null); // 重置taskId，停止轮询
            if (status.status === 'completed') {
              message.success('扫描任务完成');
              fetchStocks(selectedDate);
            } else {
              message.error('扫描任务失败');
            }
          }
        } catch (error) {
          console.error('获取扫描状态失败', error);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [taskId, selectedDate]);

  // 组件初始化时加载数据
  useEffect(() => {
    fetchStocks(selectedDate);
  }, [selectedDate]);

  // 获取异动个股列表
  const fetchStocks = async (date: string) => {
    setLoading(true);
    try {
      const data = await getAnomalyStocks(date);
      setStocks(data);
      
      // 提取行业列表
      const industrySet = new Set<string>();
      data.forEach(stock => {
        if (stock.industry) {
          industrySet.add(stock.industry);
        }
      });
      setIndustries(Array.from(industrySet).sort());
      
      // 提取规则列表
      const ruleMap = new Map<string, { label: string; value: string }>();
      data.forEach(stock => {
        stock.triggered_rules.forEach(rule => {
          if (!ruleMap.has(rule.rule_name)) {
            ruleMap.set(rule.rule_name, { label: rule.rule_chinese_name, value: rule.rule_name });
          }
        });
      });
      setRules(Array.from(ruleMap.values()).sort((a, b) => a.label.localeCompare(b.label)));
      
      // 初始化过滤后的股票列表
      setFilteredStocks(data);
    } catch (error) {
      message.error('获取异动个股列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 导出清单
  const handleExport = async () => {
    try {
      const blob = await exportAnomalyStocks(selectedDate);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `anomaly_stocks_${selectedDate}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
    }
  };

  // 查看股票详情
  const handleViewStockDetail = async (stock_code: string) => {
    // 先显示弹窗
    setStockDetailLoading(true);
    setStockDetailModalVisible(true);
    
    try {
      // 异步调用 API 获取股票详情（不包含行业风险分析）
      const stockDetail = await getAnomalyStock(stock_code, selectedDate, false);
      setSelectedStock(stockDetail);
    } catch (error) {
      message.error('获取股票详情失败');
    } finally {
      setStockDetailLoading(false);
    }
  };

  // 手动触发获取行业风险分析
  const handleGetIndustryRisk = async () => {
    if (!selectedStock) return;
    
    setIndustryRiskLoading(true);
    try {
      // 调用 API 获取包含行业风险分析的股票详情
      const stockDetail = await getAnomalyStock(selectedStock.stock_code, selectedDate, true);
      setSelectedStock(stockDetail);
    } catch (error) {
      message.error('获取行业风险分析失败');
    } finally {
      setIndustryRiskLoading(false);
    }
  };

  // 日期变化处理
  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      setSelectedIndustry('');
      setSelectedRules([]);
      fetchStocks(newDate);
    }
  };
  
  // 筛选逻辑
  const handleFilter = (industry?: string, rules?: string[]) => {
    let filtered = stocks;
    const currentIndustry = industry !== undefined ? industry : selectedIndustry;
    const currentRules = rules !== undefined ? rules : selectedRules;
    
    // 按行业筛选
    if (currentIndustry) {
      filtered = filtered.filter(stock => stock.industry === currentIndustry);
    }
    
    // 按规则筛选
    if (currentRules.length > 0) {
      filtered = filtered.filter(stock => {
        const stockRuleNames = stock.triggered_rules.map((rule: any) => rule.rule_name);
        return currentRules.some(rule => stockRuleNames.includes(rule));
      });
    }
    
    setFilteredStocks(filtered);
  };
  
  // 行业变化处理
  const handleIndustryChange = (value: string | null) => {
    setSelectedIndustry(value || '');
    handleFilter(value || '');
  };
  
  // 规则变化处理
  const handleRulesChange = (value: string[]) => {
    setSelectedRules(value);
    handleFilter(undefined, value);
  };

  // 表格列定义
  const columns = [
    {
      title: '股票代码',
      dataIndex: 'stock_code',
      key: 'stock_code',
      render: (text: string) => (
        <a onClick={() => handleViewStockDetail(text)}>{text}</a>
      ),
    },
    {
      title: '股票名称',
      dataIndex: 'stock_name',
      key: 'stock_name',
    },
    {
      title: '触发规则数',
      dataIndex: 'total_triggers',
      key: 'total_triggers',
      sorter: (a: AnomalyStock, b: AnomalyStock) => a.total_triggers - b.total_triggers,
    },
    {
      title: '所属行业',
      dataIndex: 'industry',
      key: 'industry',
    },
    {
      title: '触发规则',
      dataIndex: 'triggered_rules',
      key: 'triggered_rules',
      render: (rules: Array<{ rule_chinese_name: string }>) => (
        <Space direction="vertical" size={0}>
          {rules.map((rule, index) => (
            <Text key={index}>{rule.rule_chinese_name}</Text>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: '24px', flexWrap: 'wrap' }} align="center">
        <Select
          placeholder="选择所属行业"
          style={{ width: 200 }}
          value={selectedIndustry}
          onChange={handleIndustryChange}
          allowClear
          showSearch
          filterOption={(input, option) =>
            (option?.children as unknown as string).toLowerCase().includes(input.toLowerCase())
          }
        >
          {industries.map(industry => (
            <Select.Option key={industry} value={industry}>{industry}</Select.Option>
          ))}
        </Select>
        <Select
          placeholder="选择触发规则"
          style={{ width: 300 }}
          mode="multiple"
          value={selectedRules}
          onChange={handleRulesChange}
          allowClear
        >
          {rules.map(rule => (
            <Select.Option key={rule.value} value={rule.value}>{rule.label}</Select.Option>
          ))}
        </Select>
        <input 
          type="date" 
          value={selectedDate} 
          onChange={(e) => handleDateChange(e.target.value)}
          style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px' }}
        />
        <Button 
          type="primary" 
          icon={<ReloadOutlined />} 
          onClick={handleTriggerScan}
          loading={scanLoading}
        >
          开始扫描
        </Button>
        <Button 
          icon={<ExportOutlined />} 
          onClick={handleExport}
          disabled={stocks.length === 0}
        >
          导出清单
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={filteredStocks}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      {/* 扫描进度模态框 */}
      <Modal
        title="扫描进度"
        open={progressModalVisible}
        footer={null}
        onCancel={() => {
          setProgressModalVisible(false);
          setTaskId(null); // 重置taskId，停止轮询
        }}
      >
        {scanStatus ? (
          <div>
            <Text>状态: {scanStatus.status}</Text>
            <br />
            <Text>处理进度: {scanStatus.processed_stocks}/{scanStatus.total_stocks}</Text>
            <Progress 
              percent={scanStatus.total_stocks > 0 ? (scanStatus.processed_stocks / scanStatus.total_stocks) * 100 : 0} 
              status="active" 
            />
            {scanStatus.error_message && (
              <Text type="danger" style={{ marginTop: '16px', display: 'block' }}>
                错误信息: {scanStatus.error_message}
              </Text>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '24px' }}>
            <LoadingOutlined style={{ fontSize: '24px' }} spin />
            <Text style={{ marginLeft: '8px' }}>正在启动扫描任务...</Text>
          </div>
        )}
      </Modal>

      {/* 股票详情模态框 */}
      <Modal
        title="股票详情"
        open={stockDetailModalVisible}
        footer={null}
        onCancel={() => setStockDetailModalVisible(false)}
        width={800}
      >
        {selectedStock ? (
          <div>
            <Descriptions bordered column={2}>
              <Descriptions.Item label="股票代码">{selectedStock.stock_code}</Descriptions.Item>
              <Descriptions.Item label="股票名称">{selectedStock.stock_name}</Descriptions.Item>
              <Descriptions.Item label="扫描日期">{selectedStock.scan_date}</Descriptions.Item>
              <Descriptions.Item label="触发规则数">{selectedStock.total_triggers}</Descriptions.Item>
              <Descriptions.Item label="所属行业" span={2}>{selectedStock.industry || '未知'}</Descriptions.Item>
            </Descriptions>
            
            <div style={{ marginTop: '24px' }}>
              <Title level={5}>触发规则详情</Title>
              {selectedStock.triggered_rules.map((rule: any, index: number) => (
                <div key={index} style={{ marginBottom: '16px', padding: '12px', border: '1px solid #e8e8e8', borderRadius: '4px' }}>
                  <Space>
                    <Text strong>{rule.rule_chinese_name || rule.rule_name.replace('rule_', '')}</Text>
                    <Tooltip title={ruleDetails[rule.rule_name] || '暂无规则详情'}>
                      <InfoCircleOutlined style={{ color: '#1890ff', cursor: 'help' }} />
                    </Tooltip>
                  </Space>
                  <div style={{ marginTop: '8px' }}>
                    {Object.entries(rule.details).map(([key, value]) => (
                      <Text key={key} style={{ display: 'block' }}>{key}: {typeof value === 'number' ? value.toFixed(4) : value}</Text>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            
            <div style={{ marginTop: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <Title level={5}>行业风险分析</Title>
                {!selectedStock.industry_risk && (
                  <Button 
                    type="primary" 
                    onClick={handleGetIndustryRisk}
                    loading={industryRiskLoading}
                  >
                    获取风险分析
                  </Button>
                )}
              </div>
              {industryRiskLoading ? (
                <div style={{ 
                  padding: '48px', 
                  textAlign: 'center', 
                  border: '1px solid #e8e8e8', 
                  borderRadius: '4px'
                }}>
                  <Spin size="large" />
                  <Text style={{ marginLeft: '16px' }}>正在获取行业风险分析...</Text>
                </div>
              ) : selectedStock.industry_risk ? (
                <div style={{ 
                  padding: '16px', 
                  border: '1px solid #e8e8e8', 
                  borderRadius: '4px', 
                  backgroundColor: '#f9f9f9',
                  whiteSpace: 'pre-line',
                  fontFamily: 'Arial, sans-serif',
                  lineHeight: '1.6'
                }}>
                  <div dangerouslySetInnerHTML={{ 
                    __html: selectedStock.industry_risk
                      .replace(/### (.*?)/g, '<h3 style="margin: 16px 0 8px 0; font-size: 16px; font-weight: 600;">$1</h3>')
                      .replace(/## (.*?)/g, '<h2 style="margin: 20px 0 12px 0; font-size: 18px; font-weight: 600;">$1</h2>')
                      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                      .replace(/\* ([^*]+)/g, '<li style="margin-left: 20px; margin-bottom: 4px;">$1</li>')
                      .replace(/\n\n/g, '</p><p>')
                      .replace(/^(?!<h|<li|<p).*/g, '<p>$&</p>')
                  }} />
                </div>
              ) : (
                <div style={{ 
                  padding: '48px', 
                  border: '1px dashed #e8e8e8', 
                  borderRadius: '4px', 
                  textAlign: 'center',
                  backgroundColor: '#fafafa'
                }}>
                  <Text type="secondary">点击上方按钮获取行业风险分析</Text>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '48px' }}>
            <Text>暂无股票详情</Text>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default AnomalyList;
