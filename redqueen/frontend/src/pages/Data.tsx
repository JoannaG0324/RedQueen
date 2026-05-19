import React, { useState } from 'react';
import { Checkbox, Button, Typography, Space, Alert, Card, Modal, Radio } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { api } from '../api/api';

const { Title, Text } = Typography;

interface Task {
  id: string;
  name: string;
  description: string;
  isSelected: boolean;
  status: 'idle' | 'running' | 'completed' | 'failed';
  result: string;
  requiresPage?: boolean; // 是否需要页码选择
}

const Data: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([
    {
      id: 'update_industry_flow_data',
      name: '更新行业板块资金流向数据(AK)',
      description: '更新行业板块的资金流向数据，包括净流入、成交量等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'update_stock_flow',
      name: '更新股票资金流数据(AK)',
      description: '更新股票的资金流数据，包括流入资金、流出资金、净额等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'update_stock_ztb_data',
      name: '更新股票涨停板数据(AK)',
      description: '更新股票的涨停板数据，包括封板资金、首次封板时间等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'update_stock_spot_data',
      name: '更新股票实时数据(AK)',
      description: '更新股票的实时数据，包括最新价、涨跌幅、成交量等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'update_stock_daily_backup',
      name: '更新股票实时数据(Browser)',
      description: '更新股票的每日交易数据，包括开盘价、收盘价、成交量等',
      isSelected: false,
      status: 'idle',
      result: '',
      requiresPage: true
    },
    {
      id: 'update_industry_ths_index_daily',
      name: '更新行业板块日数据(Browser)',
      description: '更新行业板块的日数据，包括开盘价、收盘价、成交量等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'industry_flow_calc',
      name: '计算：行业板块资金流',
      description: '计算行业板块的资金流指标，包括3天/5天/10天/20天的移动平均值',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'daily_process_industry_indicators',
      name: '计算：行业基础量价指标',
      description: '计算行业的基础量价指标，包括移动平均线、ATR等',
      isSelected: false,
      status: 'idle',
      result: ''
    },
    {
      id: 'daily_process_stock_indicators',
      name: '计算：个股量价指标',
      description: '计算个股的量价指标，包括移动平均线、ATR、持续增长天数等',
      isSelected: false,
      status: 'idle',
      result: ''
    }
  ]);

  // 按类型选择状态
  const [dataUpdateSelected, setDataUpdateSelected] = useState(false);
  const [calcTasksSelected, setCalcTasksSelected] = useState(false);

  const [isExecuting, setIsExecuting] = useState(false);
  const [pageModalVisible, setPageModalVisible] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');
  const [selectedPage, setSelectedPage] = useState<string>('1');
  const [isStopping, setIsStopping] = useState(false);

  const handleTaskToggle = (taskId: string) => {
    setTasks(prevTasks =>
      prevTasks.map(task =>
        task.id === taskId ? { ...task, isSelected: !task.isSelected } : task
      )
    );
  };

  const handleDataUpdateToggle = () => {
    const newDataUpdateSelected = !dataUpdateSelected;
    setDataUpdateSelected(newDataUpdateSelected);
    setTasks(prevTasks =>
      prevTasks.map(task => {
        // 数据更新任务：任务1-6
        const dataUpdateTaskIds = [
          'update_industry_flow_data',
          'update_stock_flow',
          'update_stock_ztb_data',
          'update_stock_spot_data',
          'update_stock_daily_backup',
          'update_industry_ths_index_daily'
        ];
        if (dataUpdateTaskIds.includes(task.id)) {
          return { ...task, isSelected: newDataUpdateSelected };
        }
        return task;
      })
    );
  };

  const handleCalcTasksToggle = () => {
    const newCalcTasksSelected = !calcTasksSelected;
    setCalcTasksSelected(newCalcTasksSelected);
    setTasks(prevTasks =>
      prevTasks.map(task => {
        // 计算任务：任务7-9
        const calcTaskIds = [
          'industry_flow_calc',
          'daily_process_industry_indicators',
          'daily_process_stock_indicators'
        ];
        if (calcTaskIds.includes(task.id)) {
          return { ...task, isSelected: newCalcTasksSelected };
        }
        return task;
      })
    );
  };

  const handleExecute = async () => {
    const selectedTasks = tasks.filter(task => task.isSelected);
    if (selectedTasks.length === 0) {
      return;
    }

    // 检查是否有任务需要页码选择
    const taskRequiringPage = selectedTasks.find(task => task.requiresPage);
    if (taskRequiringPage) {
      // 显示页码选择弹窗
      setSelectedTaskId(taskRequiringPage.id);
      setPageModalVisible(true);
      return;
    }

    // 执行不需要页码的任务
    executeTasks(selectedTasks);
  };

  const executeTasks = async (tasksToExecute: Task[]) => {
    setIsExecuting(true);

    // 更新任务状态为运行中
    setTasks(prevTasks =>
      prevTasks.map(task =>
        tasksToExecute.some(t => t.id === task.id)
          ? { ...task, status: 'running', result: '' }
          : task
      )
    );

    // 逐个执行选中的任务
    for (const task of tasksToExecute) {
      try {
        // 调用后端API执行任务
        const response = await api.post('/data/execute', null, {
          params: {
            task_id: task.id,
            page: task.id === 'update_stock_daily_backup' ? selectedPage : undefined
          }
        });

        // 构建执行结果
        const result = `任务 ${task.name} 执行完成\n执行时间: ${new Date().toLocaleString()}\n状态: ${response.data.status}\n消息: ${response.data.message}`;

        // 根据后端返回的status设置任务状态
        const taskStatus = response.data.status === 'completed' ? 'completed' : 'failed';

        // 更新任务状态和结果
        setTasks(prevTasks =>
          prevTasks.map(t =>
            t.id === task.id ? { ...t, status: taskStatus, result } : t
          )
        );
      } catch (error: any) {
        console.error('执行任务失败:', error);
        // 构建错误信息
        const errorMessage = error.response?.data?.detail || '执行任务时发生错误';
        const result = `任务 ${task.name} 执行失败\n执行时间: ${new Date().toLocaleString()}\n错误信息: ${errorMessage}`;
        // 更新失败的任务状态
        setTasks(prevTasks =>
          prevTasks.map(t =>
            t.id === task.id ? { ...t, status: 'failed', result } : t
          )
        );
      }
    }

    setIsExecuting(false);
  };

  const handlePageSelect = () => {
    setPageModalVisible(false);
    // 执行选中的任务
    executeTasks(tasks.filter(task => task.isSelected));
  };

  const handleStopTasks = async () => {
    setIsStopping(true);
    try {
      // 调用后端API来终止任务
      const response = await api.post('/data/stop');
      
      // 重置任务状态
      setTasks(prevTasks =>
        prevTasks.map(task => ({
          ...task,
          status: 'idle',
          result: '任务已终止'
        }))
      );
      setIsExecuting(false);
    } catch (error) {
      console.error('终止任务失败:', error);
      // 即使API调用失败，也重置前端状态
      setTasks(prevTasks =>
        prevTasks.map(task => ({
          ...task,
          status: 'idle',
          result: '任务已终止'
        }))
      );
      setIsExecuting(false);
    } finally {
      setIsStopping(false);
    }
  };

  const getStatusIcon = (status: Task['status']) => {
    switch (status) {
      case 'running':
        return <LoadingOutlined spin />;
      case 'completed':
        return <span style={{ color: '#52c41a' }}>✓</span>;
      case 'failed':
        return <span style={{ color: '#ff4d4f' }}>✗</span>;
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <Title level={3}>数据管理</Title>
      <Text type="secondary">执行数据获取和更新任务</Text>
      
      <Card style={{ marginTop: '24px' }}>
        <Space orientation="vertical" style={{ width: '100%' }}>
          {/* 数据更新任务 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
            <Checkbox
              checked={dataUpdateSelected}
              onChange={handleDataUpdateToggle}
            />
            <Space style={{ marginLeft: '8px' }}>
              <Text strong>数据更新任务</Text>
              <Text type="secondary">选择全部数据更新任务</Text>
            </Space>
          </div>
          
          {/* 数据更新任务列表 */}
          {tasks.filter(task => [
            'update_industry_flow_data',
            'update_stock_flow',
            'update_stock_ztb_data',
            'update_stock_spot_data',
            'update_stock_daily_backup',
            'update_industry_ths_index_daily'
          ].includes(task.id)).map(task => (
            <div key={task.id} style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                <Checkbox
                  checked={task.isSelected}
                  onChange={() => handleTaskToggle(task.id)}
                />
                <Space style={{ marginLeft: '8px' }}>
                  <Text strong>{task.name}</Text>
                  <Text type="secondary">{task.description}</Text>
                  {getStatusIcon(task.status)}
                </Space>
              </div>
              {task.result && (
                <Alert
                  description={
                    <div style={{ color: task.status === 'completed' ? '' : '#ff4d4f' }}>
                      {task.result}
                    </div>
                  }
                  type={task.status === 'completed' ? 'success' : 'error'}
                  style={{ marginLeft: '32px', marginTop: '8px' }}
                />
              )}
            </div>
          ))}
          
          {/* 计算任务 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
            <Checkbox
              checked={calcTasksSelected}
              onChange={handleCalcTasksToggle}
            />
            <Space style={{ marginLeft: '8px' }}>
              <Text strong>计算任务</Text>
              <Text type="secondary">选择全部计算任务</Text>
            </Space>
          </div>
          
          {/* 计算任务列表 */}
          {tasks.filter(task => [
            'industry_flow_calc',
            'daily_process_industry_indicators',
            'daily_process_stock_indicators'
          ].includes(task.id)).map(task => (
            <div key={task.id} style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                <Checkbox
                  checked={task.isSelected}
                  onChange={() => handleTaskToggle(task.id)}
                />
                <Space style={{ marginLeft: '8px' }}>
                  <Text strong>{task.name}</Text>
                  <Text type="secondary">{task.description}</Text>
                  {getStatusIcon(task.status)}
                </Space>
              </div>
              {task.result && (
                <Alert
                  description={
                    <div style={{ color: task.status === 'completed' ? '' : '#ff4d4f' }}>
                      {task.result}
                    </div>
                  }
                  type={task.status === 'completed' ? 'success' : 'error'}
                  style={{ marginLeft: '32px', marginTop: '8px' }}
                />
              )}
            </div>
          ))}
          
          <Space>
            <Button
              type="primary"
              onClick={handleExecute}
              loading={isExecuting}
              disabled={tasks.filter(t => t.isSelected).length === 0 || isExecuting}
            >
              执行选中任务
            </Button>
            <Button
              danger
              onClick={handleStopTasks}
              loading={isStopping}
              disabled={!isExecuting}
            >
              终止全部任务
            </Button>
          </Space>
        </Space>
      </Card>

      {/* 页码选择弹窗 */}
      <Modal
        title="选择页码范围"
        open={pageModalVisible}
        onOk={handlePageSelect}
        onCancel={() => setPageModalVisible(false)}
        okText="确定"
        cancelText="取消"
      >
        <p>请选择要运行的页码范围：</p>
        <Radio.Group value={selectedPage} onChange={e => setSelectedPage(e.target.value)}>
          <Radio value="1">1-50</Radio><br />
          <Radio value="51">51-100</Radio><br />
          <Radio value="101">101-150</Radio><br />
          <Radio value="151">151-200</Radio><br />
          <Radio value="201">201-250</Radio><br />
          <Radio value="251">251-</Radio>
        </Radio.Group>
      </Modal>
    </div>
  );
};

export default Data;