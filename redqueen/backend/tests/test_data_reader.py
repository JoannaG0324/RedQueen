import unittest
from datetime import date, timedelta
from unittest.mock import Mock, MagicMock
from sqlalchemy.orm import Session

from src.data.data_reader import DataReader
from src.models.stock_models import StockDailyQfq, StockDailyQfqCalc, StockDailyFlow, StockInfo


class TestDataReader(unittest.TestCase):
    """数据读取器单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建模拟数据库会话
        self.mock_db = Mock(spec=Session)
        self.data_reader = DataReader(self.mock_db)
        
        # 测试日期
        self.test_date = date(2024, 1, 31)
        self.start_date = self.test_date - timedelta(days=60)
    
    def test_get_stock_list(self):
        """测试获取股票列表"""
        # 模拟股票数据
        mock_stocks = [
            Mock(stock_code="600000", stock_name="浦发银行"),
            Mock(stock_code="600519", stock_name="贵州茅台")
        ]
        
        # 配置模拟行为
        self.mock_db.query.return_value.all.return_value = mock_stocks
        
        # 执行测试
        result = self.data_reader.get_stock_list()
        
        # 验证结果
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["stock_code"], "600000")
        self.assertEqual(result[0]["stock_name"], "浦发银行")
    
    def test_get_stock_data_by_date_no_data(self):
        """测试获取股票数据（无数据情况）"""
        # 配置模拟行为 - 无价格数据
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        
        # 执行测试
        result = self.data_reader.get_stock_data_by_date("600000", self.test_date)
        
        # 验证结果
        self.assertIsNone(result)
    
    def test_validate_data_insufficient_length(self):
        """测试数据校验（长度不足）"""
        # 创建长度不足的数据
        data = {
            "dates": ["2024-01-01"] * 29,  # 只有29天数据
            "close": [100] * 29,
            "volume": [1000000] * 29,
            "ma20": [100] * 29
        }
        
        # 执行测试
        result = self.data_reader._validate_data(data)
        
        # 验证结果
        self.assertFalse(result)
    
    def test_validate_data_insufficient_valid_data(self):
        """测试数据校验（有效数据不足）"""
        # 创建有效数据不足的数据
        data = {
            "dates": ["2024-01-01"] * 60,
            "close": [100] * 40 + [None] * 20,  # 只有40个有效值，不足80%
            "volume": [1000000] * 60,
            "ma20": [100] * 60
        }
        
        # 执行测试
        result = self.data_reader._validate_data(data)
        
        # 验证结果
        self.assertFalse(result)
    
    def test_validate_data_valid(self):
        """测试数据校验（有效数据）"""
        # 创建有效数据
        data = {
            "dates": ["2024-01-01"] * 60,
            "close": [100] * 55 + [None] * 5,  # 55个有效值，超过80%
            "volume": [1000000] * 60,
            "ma20": [100] * 60
        }
        
        # 执行测试
        result = self.data_reader._validate_data(data)
        
        # 验证结果
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
