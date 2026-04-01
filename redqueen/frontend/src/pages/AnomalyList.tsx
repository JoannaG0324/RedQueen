import React, { useState, useEffect } from 'react';
import { Button, Table, message, Space, Typography, Progress, Modal, Descriptions, Spin } from 'antd';
import { ReloadOutlined, ExportOutlined, LoadingOutlined } from '@ant-design/icons';
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

const AnomalyList: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<any>(null);
  const [stocks, setStocks] = useState<AnomalyStock[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [progressModalVisible, setProgressModalVisible] = useState(false);
  const [stockDetailModalVisible, setStockDetailModalVisible] = useState(false);
  const [selectedStock, setSelectedStock] = useState<any>(null);
  const [stockDetailLoading, setStockDetailLoading] = useState(false);

  // 触发扫描
  const handleTriggerScan = async () => {
    setScanLoading(true);
    try {
      const result = await triggerScan();
      setTaskId(result.task_id);
      setProgressModalVisible(true);
      message.success('扫描任务已启动');
    } catch (error) {
      message.error('启动扫描任务失败');
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

  // 获取异动个股列表
  const fetchStocks = async (date: string) => {
    setLoading(true);
    try {
      const data = await getAnomalyStocks(date);
      setStocks(data);
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
    setStockDetailLoading(true);
    try {
      const stockDetail = await getAnomalyStock(stock_code, selectedDate);
      setSelectedStock(stockDetail);
      setStockDetailModalVisible(true);
    } catch (error) {
      message.error('获取股票详情失败');
    } finally {
      setStockDetailLoading(false);
    }
  };

  // 日期变化处理
  const handleDateChange = (date: any) => {
    if (date) {
      const newDate = typeof date === 'string' ? date : date.format('YYYY-MM-DD');
      setSelectedDate(newDate);
      fetchStocks(newDate);
    }
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
      <Space style={{ marginBottom: '24px' }}>
        <Button 
          type="primary" 
          icon={<ReloadOutlined />} 
          onClick={handleTriggerScan}
          loading={scanLoading}
        >
          开始扫描
        </Button>
        <input 
          type="date" 
          value={selectedDate} 
          onChange={(e) => handleDateChange(e.target.value)}
          style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px' }}
        />
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
        dataSource={stocks}
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
        {stockDetailLoading ? (
          <div style={{ textAlign: 'center', padding: '48px' }}>
            <Spin size="large" />
            <Text style={{ marginLeft: '16px' }}>正在加载股票详情...</Text>
          </div>
        ) : selectedStock ? (
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
                  <Text strong>{rule.rule_chinese_name || rule.rule_name.replace('rule_', '')}</Text>
                  <div style={{ marginTop: '8px' }}>
                    {Object.entries(rule.details).map(([key, value]) => (
                      <Text key={key} style={{ display: 'block' }}>{key}: {value}</Text>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            
            {selectedStock.industry_risk && (
              <div style={{ marginTop: '24px' }}>
                <Title level={5}>行业风险分析</Title>
                <div style={{ padding: '12px', border: '1px solid #e8e8e8', borderRadius: '4px', backgroundColor: '#f9f9f9' }}>
                  <Text>{selectedStock.industry_risk}</Text>
                </div>
              </div>
            )}
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
