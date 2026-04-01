import React, { useState, useEffect } from 'react';
import { useParams, useLocation, Link, useNavigate } from 'react-router-dom';
import { Typography, Descriptions, Card, Spin, message, Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { getAnomalyStock } from '../api/api';

const { Title, Text, Paragraph } = Typography;

interface TriggeredRule {
  rule_name: string;
  details: any;
}

interface StockDetailData {
  id: number;
  stock_code: string;
  stock_name: string;
  scan_date: string;
  total_triggers: number;
  triggered_rules: TriggeredRule[];
  industry: string;
  industry_code: string;
  industry_risk: string;
  created_at: string;
}

const StockDetail: React.FC = () => {
  const { stockCode } = useParams<{ stockCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stockData, setStockData] = useState<StockDetailData | null>(null);

  // 从URL参数中获取扫描日期
  const getScanDate = () => {
    const params = new URLSearchParams(location.search);
    return params.get('scan_date') || new Date().toISOString().split('T')[0];
  };

  const scanDate = getScanDate();

  // 获取个股详情
  useEffect(() => {
    const fetchStockDetail = async () => {
      if (!stockCode) return;
      setLoading(true);
      try {
        const data = await getAnomalyStock(stockCode, scanDate);
        setStockData(data);
      } catch (error) {
        message.error('获取个股详情失败');
      } finally {
        setLoading(false);
      }
    };

    fetchStockDetail();
  }, [stockCode, scanDate]);

  // 规则名称映射
  const ruleNameMap: Record<string, string> = {
    rule_ma_crossover: '均线交叉趋势异动',
    rule_trendline_breakout: '趋势线突破异动',
    rule_dow_theory: '道氏高低点趋势异动',
    rule_macd_divergence: 'MACD趋势背离异动',
    rule_bollinger_band_breakout: '布林带通道突破异动',
    rule_quantile_regression: '分位数回归趋势异动',
    rule_volume_price_divergence: '量价背离趋势异动',
    rule_obv_trend: 'OBV能量潮趋势异动',
    rule_capital_flow: '主力资金流趋势异动',
    rule_turnover_trend: '换手率趋势异动',
    rule_atr_volatility: 'ATR波动率异动',
    rule_volatility_expansion: '波动率收敛-发散异动',
    rule_amplitude_trend: '振幅异动趋势识别'
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '48px' }}>
        <Spin size="large" />
        <Text style={{ display: 'block', marginTop: '16px' }}>加载中...</Text>
      </div>
    );
  }

  if (!stockData) {
    return (
      <div style={{ textAlign: 'center', padding: '48px' }}>
        <Text type="danger">个股详情不存在</Text>
        <Button type="primary" style={{ marginTop: '16px' }} onClick={() => navigate('/')}>
          返回列表
        </Button>
      </div>
    );
  }

  return (
    <div>
      <Button 
        icon={<ArrowLeftOutlined />} 
        onClick={() => navigate('/')}
        style={{ marginBottom: '24px' }}
      >
        返回列表
      </Button>

      <Title level={4}>{stockData.stock_name} ({stockData.stock_code})</Title>

      <Card style={{ marginBottom: '24px' }}>
        <Descriptions column={2}>
          <Descriptions.Item label="扫描日期">{stockData.scan_date}</Descriptions.Item>
          <Descriptions.Item label="触发规则数">{stockData.total_triggers}</Descriptions.Item>
          <Descriptions.Item label="所属行业">{stockData.industry || '未知'}</Descriptions.Item>
          <Descriptions.Item label="行业代码">{stockData.industry_code || '未知'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="触发规则详情" style={{ marginBottom: '24px' }}>
        {stockData.triggered_rules.map((rule, index) => (
          <div key={index} style={{ marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid #f0f0f0' }}>
            <Title level={5}>{ruleNameMap[rule.rule_name] || rule.rule_name}</Title>
            <Descriptions column={1} size="small">
              {Object.entries(rule.details).map(([key, value]) => (
                <Descriptions.Item key={key} label={key}>
                  {typeof value === 'object' ? JSON.stringify(value) : 
                    typeof value === 'number' ? value.toFixed(4) : value}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </div>
        ))}
      </Card>

      {stockData.industry_risk && (
        <Card title="行业风险分析">
          <Paragraph>{stockData.industry_risk}</Paragraph>
        </Card>
      )}
    </div>
  );
};

export default StockDetail;
