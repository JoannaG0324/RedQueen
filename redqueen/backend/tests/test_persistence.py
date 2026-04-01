import unittest
from datetime import date, datetime
from unittest.mock import Mock, MagicMock
from sqlalchemy.orm import Session

from src.models.persistence_models import (
    PersistenceManager, AnomalyStock, IndustryRisk, ScanTask, TaskStatus
)


class TestPersistenceManager(unittest.TestCase):
    """数据持久化管理器单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建模拟数据库会话
        self.mock_db = Mock(spec=Session)
        self.persistence_manager = PersistenceManager(self.mock_db)
        
        # 测试数据
        self.test_date = date(2024, 1, 31)
        self.test_task_id = "test-task-123"
    
    def test_save_anomaly_stock(self):
        """测试保存异动个股"""
        # 测试数据
        stock_data = {
            "stock_code": "600000",
            "stock_name": "浦发银行",
            "scan_date": self.test_date,
            "total_triggers": 2,
            "triggered_rules": [{"rule_name": "rule_ma_crossover", "details": {}}],
            "industry": "银行",
            "industry_code": "601"
        }
        
        # 模拟返回值
        mock_stock = Mock(spec=AnomalyStock)
        self.mock_db.add.return_value = None
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # 执行测试
        result = self.persistence_manager.save_anomaly_stock(stock_data)
        
        # 验证结果
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once()
    
    def test_save_batch_anomaly_stocks(self):
        """测试批量保存异动个股"""
        # 测试数据
        stocks_data = [
            {
                "stock_code": "600000",
                "stock_name": "浦发银行",
                "scan_date": self.test_date,
                "total_triggers": 2,
                "triggered_rules": [{"rule_name": "rule_ma_crossover", "details": {}}],
                "industry": "银行",
                "industry_code": "601"
            },
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "scan_date": self.test_date,
                "total_triggers": 1,
                "triggered_rules": [{"rule_name": "rule_bollinger_band_breakout", "details": {}}],
                "industry": "白酒",
                "industry_code": "600"
            }
        ]
        
        # 模拟返回值
        self.mock_db.add_all.return_value = None
        self.mock_db.commit.return_value = None
        
        # 执行测试
        result = self.persistence_manager.save_batch_anomaly_stocks(stocks_data)
        
        # 验证结果
        self.mock_db.add_all.assert_called_once()
        self.mock_db.commit.assert_called_once()
        self.assertEqual(len(result), 2)
    
    def test_get_anomaly_stocks_by_date(self):
        """测试按日期获取异动个股"""
        # 模拟返回值
        mock_stocks = [Mock(spec=AnomalyStock), Mock(spec=AnomalyStock)]
        self.mock_db.query.return_value.filter.return_value.all.return_value = mock_stocks
        
        # 执行测试
        result = self.persistence_manager.get_anomaly_stocks_by_date(self.test_date)
        
        # 验证结果
        self.assertEqual(len(result), 2)
        self.mock_db.query.assert_called_once_with(AnomalyStock)
    
    def test_get_anomaly_stock_by_code_and_date(self):
        """测试按股票代码和日期获取异动个股"""
        # 模拟返回值
        mock_stock = Mock(spec=AnomalyStock)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_stock
        
        # 执行测试
        result = self.persistence_manager.get_anomaly_stock_by_code_and_date("600000", self.test_date)
        
        # 验证结果
        self.assertEqual(result, mock_stock)
        self.mock_db.query.assert_called_once_with(AnomalyStock)
    
    def test_save_industry_risk_new(self):
        """测试保存行业风险（新数据）"""
        # 测试数据
        risk_data = {
            "industry": "银行",
            "analyze_date": self.test_date,
            "risk_analysis": "银行行业风险分析"
        }
        
        # 模拟返回值 - 不存在现有数据
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_risk = Mock(spec=IndustryRisk)
        self.mock_db.add.return_value = None
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # 执行测试
        result = self.persistence_manager.save_industry_risk(risk_data)
        
        # 验证结果
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
    
    def test_save_industry_risk_existing(self):
        """测试保存行业风险（更新现有数据）"""
        # 测试数据
        risk_data = {
            "industry": "银行",
            "analyze_date": self.test_date,
            "risk_analysis": "银行行业风险分析（更新）"
        }
        
        # 模拟返回值 - 存在现有数据
        mock_existing = Mock(spec=IndustryRisk)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_existing
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # 执行测试
        result = self.persistence_manager.save_industry_risk(risk_data)
        
        # 验证结果
        self.assertEqual(mock_existing.risk_analysis, "银行行业风险分析（更新）")
        self.mock_db.commit.assert_called_once()
    
    def test_get_industry_risk(self):
        """测试获取行业风险"""
        # 模拟返回值
        mock_risk = Mock(spec=IndustryRisk)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_risk
        
        # 执行测试
        result = self.persistence_manager.get_industry_risk("银行", self.test_date)
        
        # 验证结果
        self.assertEqual(result, mock_risk)
        self.mock_db.query.assert_called_once_with(IndustryRisk)
    
    def test_save_scan_task(self):
        """测试保存扫描任务"""
        # 测试数据
        task_data = {
            "task_id": self.test_task_id,
            "status": TaskStatus.PENDING,
            "total_stocks": 1000
        }
        
        # 模拟返回值
        mock_task = Mock(spec=ScanTask)
        self.mock_db.add.return_value = None
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # 执行测试
        result = self.persistence_manager.save_scan_task(task_data)
        
        # 验证结果
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()
    
    def test_update_scan_task(self):
        """测试更新扫描任务"""
        # 测试数据
        update_data = {
            "status": TaskStatus.COMPLETED,
            "end_time": datetime.now(),
            "processed_stocks": 1000
        }
        
        # 模拟返回值
        mock_task = Mock(spec=ScanTask)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        self.mock_db.commit.return_value = None
        self.mock_db.refresh.return_value = None
        
        # 执行测试
        result = self.persistence_manager.update_scan_task(self.test_task_id, update_data)
        
        # 验证结果
        self.assertEqual(result, mock_task)
        self.assertEqual(mock_task.status, TaskStatus.COMPLETED)
        self.mock_db.commit.assert_called_once()
    
    def test_get_scan_task(self):
        """测试获取扫描任务"""
        # 模拟返回值
        mock_task = Mock(spec=ScanTask)
        self.mock_db.query.return_value.filter.return_value.first.return_value = mock_task
        
        # 执行测试
        result = self.persistence_manager.get_scan_task(self.test_task_id)
        
        # 验证结果
        self.assertEqual(result, mock_task)
        self.mock_db.query.assert_called_once_with(ScanTask)
    
    def test_get_scan_tasks_by_status(self):
        """测试按状态获取扫描任务"""
        # 模拟返回值
        mock_tasks = [Mock(spec=ScanTask), Mock(spec=ScanTask)]
        self.mock_db.query.return_value.filter.return_value.all.return_value = mock_tasks
        
        # 执行测试
        result = self.persistence_manager.get_scan_tasks_by_status(TaskStatus.RUNNING)
        
        # 验证结果
        self.assertEqual(len(result), 2)
        self.mock_db.query.assert_called_once_with(ScanTask)


if __name__ == "__main__":
    unittest.main()
