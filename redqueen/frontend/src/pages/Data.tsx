import React, { useState } from 'react';
import { Checkbox, Button, Typography, Space, Alert, Card, Modal, Radio } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { api, triggerScan, getScanStatus } from '../api/api';

const { Title, Text } = Typography;

interface Task {
  id: string;
  name: string;
  description: string;
  isSelected: boolean;
  status: 'idle' | 'running' | 'completed' | 'failed';
  result: string;
  requiresPage?: boolean; // 是否需要页码选择
  requiresDate?: boolean; // 是否需要日期选择
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
    },
    {
      id: 'anomaly_scan',
      name: '计算：异动扫描',
      description: '执行异动扫描任务，识别符合异动规则的股票',
      isSelected: false,
      status: 'idle',
      result: '',
      requiresDate: true // 需要日期选择
    }
  ]);

  // 按类型选择状态
  const [dataUpdateSelected, setDataUpdateSelected] = useState(false);
  const [calcTasksSelected, setCalcTasksSelected] = useState(false);
  const [otherTasksSelected, setOtherTasksSelected] = useState(false);

  const [isExecuting, setIsExecuting] = useState(false);
  const [pageModalVisible, setPageModalVisible] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string>('');
  const [selectedPage, setSelectedPage] = useState<string>('1');
  const [customStartPage, setCustomStartPage] = useState<string>('');
  const [customEndPage, setCustomEndPage] = useState<string>('');
  const [useCustomRange, setUseCustomRange] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [dateModalVisible, setDateModalVisible] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);

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
        // 计算任务
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

  const handleOtherTasksToggle = () => {
    const newOtherTasksSelected = !otherTasksSelected;
    setOtherTasksSelected(newOtherTasksSelected);
    setTasks(prevTasks =>
      prevTasks.map(task => {
        // 其他计算任务
        const otherTaskIds = ['anomaly_scan'];
        if (otherTaskIds.includes(task.id)) {
          return { ...task, isSelected: newOtherTasksSelected };
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

    // 检查是否有任务需要日期选择
    const taskRequiringDate = selectedTasks.find(task => task.requiresDate);
    if (taskRequiringDate) {
      // 显示日期选择弹窗
      setSelectedTaskId(taskRequiringDate.id);
      setDateModalVisible(true);
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

    // 执行不需要额外参数的任务
    executeTasks(selectedTasks);
  };

  const executeTasks = async (tasksToExecute: Task[], page?: string, targetDate?: string) => {
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
        let response;
        let result;
        let taskStatus: 'completed' | 'failed' = 'completed';

        // 异动扫描任务使用专门的扫描API
        if (task.id === 'anomaly_scan') {
          // 触发扫描
          const scanResult = await triggerScan(targetDate);
          const scanTaskId = scanResult.task_id;
          
          // 先获取一次状态
          let scanStatus = await getScanStatus(scanTaskId);
          
          // 轮询扫描状态，直到完成或失败
          while (scanStatus && scanStatus.status !== 'completed' && scanStatus.status !== 'failed' && scanStatus.status !== 'COMPLETED' && scanStatus.status !== 'FAILED') {
            await new Promise(resolve => setTimeout(resolve, 2000));
            scanStatus = await getScanStatus(scanTaskId);
          }

          if (scanStatus && (scanStatus.status === 'completed' || scanStatus.status === 'COMPLETED')) {
            result = `任务 ${task.name} 执行完成\n执行时间: ${new Date().toLocaleString()}\n状态: completed\n扫描日期: ${targetDate}\n扫描结果: 已识别异动股票`;
            taskStatus = 'completed';
          } else {
            result = `任务 ${task.name} 执行失败\n执行时间: ${new Date().toLocaleString()}\n状态: failed\n错误信息: ${scanStatus?.message || '扫描任务失败'}`;
            taskStatus = 'failed';
          }
        } else {
          // 其他任务使用通用的执行API
          response = await api.post('/data/execute', null, {
            params: {
              task_id: task.id,
              page: task.id === 'update_stock_daily_backup' ? page : undefined,
              target_date: task.id === 'anomaly_scan' ? targetDate : undefined
            }
          });

          result = `任务 ${task.name} 执行完成\n执行时间: ${new Date().toLocaleString()}\n状态: ${response.data.status}\n消息: ${response.data.message}`;
          taskStatus = response.data.status === 'completed' ? 'completed' : 'failed';
        }

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
    // 构建当前的页码参数
    let currentPage = selectedPage;
    if (useCustomRange && customStartPage) {
      currentPage = customEndPage ? `${customStartPage}-${customEndPage}` : `${customStartPage}-`;
      setSelectedPage(currentPage);
    }
    // 执行选中的任务，并传递当前的页码参数
    executeTasks(tasks.filter(task => task.isSelected), currentPage);
  };

  const handleDateSelect = () => {
    setDateModalVisible(false);
    // 执行选中的任务，并传递日期参数
    executeTasks(tasks.filter(task => task.isSelected), undefined, selectedDate);
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
      <Card style={{ marginTop: '24px' }}>
        <Space orientation="vertical" style={{ width: '100%' }}>
          {/* 操作按钮 */}
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '16px' }}>
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
          </div>
          
          {/* 数据更新任务 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
            <Checkbox
              checked={dataUpdateSelected}
              onChange={handleDataUpdateToggle}
            />
            <Space style={{ marginLeft: '8px' }}>
              <Text strong>-- 数据更新任务 --</Text>
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
              <Text strong>-- 计算任务 --</Text>
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
          
          {/* 其他计算任务 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
            <Checkbox
              checked={otherTasksSelected}
              onChange={handleOtherTasksToggle}
            />
            <Space style={{ marginLeft: '8px' }}>
              <Text strong>-- 其他计算任务 --</Text>
              <Text type="secondary">选择全部其他计算任务</Text>
            </Space>
          </div>
          
          {/* 其他计算任务列表 */}
          {tasks.filter(task => [
            'anomaly_scan'
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
        </Space>
      </Card>

      {/* 页码选择弹窗 */}
      <Modal
        title="选择页码范围"
        open={pageModalVisible}
        onOk={handlePageSelect}
        onCancel={() => {
          setPageModalVisible(false);
          setUseCustomRange(false);
          setCustomStartPage('');
          setCustomEndPage('');
        }}
        okText="确定"
        cancelText="取消"
      >
        <p>请选择要运行的页码范围：</p>
        <Radio.Group value={useCustomRange ? 'custom' : selectedPage} onChange={e => {
          if (e.target.value === 'custom') {
            setUseCustomRange(true);
          } else {
            setUseCustomRange(false);
            setSelectedPage(e.target.value);
          }
        }}>
          <Radio value="1">1-50</Radio><br />
          <Radio value="51">51-100</Radio><br />
          <Radio value="101">101-150</Radio><br />
          <Radio value="151">151-200</Radio><br />
          <Radio value="201">201-250</Radio><br />
          <Radio value="251">251-</Radio><br />
          <Radio value="custom">自定义范围</Radio>
        </Radio.Group>
        {useCustomRange && (
          <div style={{ marginTop: 16 }}>
            <p>请输入自定义页码范围：</p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="number"
                placeholder="开始页"
                value={customStartPage}
                onChange={e => {
                  const startPage = e.target.value;
                  setCustomStartPage(startPage);
                  // 如果结束页为空或与开始页相同，自动填充结束页为开始页
                  if (!customEndPage || customEndPage === customStartPage) {
                    setCustomEndPage(startPage);
                  }
                }}
                style={{ width: 100, padding: 8, border: '1px solid #d9d9d9', borderRadius: 4 }}
              />
              <span>到</span>
              <input
                type="number"
                placeholder="结束页（可选）"
                value={customEndPage}
                onChange={e => setCustomEndPage(e.target.value)}
                style={{ width: 100, padding: 8, border: '1px solid #d9d9d9', borderRadius: 4 }}
              />
            </div>
            <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
              提示：只输入开始页表示从该页开始到最后一页
            </p>
          </div>
        )}
      </Modal>

      {/* 日期选择弹窗 */}
      <Modal
        title="选择扫描日期"
        open={dateModalVisible}
        onOk={handleDateSelect}
        onCancel={() => {
          setDateModalVisible(false);
        }}
        okText="确定"
        cancelText="取消"
      >
        <p>请选择异动扫描的目标日期：</p>
        <input
          type="date"
          value={selectedDate}
          onChange={e => setSelectedDate(e.target.value)}
          style={{ padding: '4px 11px', border: '1px solid #d9d9d9', borderRadius: '4px', height: '32px', width: '100%', marginTop: 16 }}
        />
        <p style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
          提示：请选择有效的交易日
        </p>
      </Modal>
    </div>
  );
};

export default Data;