import unittest
import numpy as np
from src.engine.rule_engine import RuleEngine


class TestRuleEngine(unittest.TestCase):
    """规则引擎单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.rule_engine = RuleEngine()
        
        # 创建测试数据
        self.test_data = {
            "dates": [f"2024-01-{i:02d}" for i in range(1, 61)],
            "close": np.linspace(100, 150, 60).tolist(),
            "high": np.linspace(101, 151, 60).tolist(),
            "low": np.linspace(99, 149, 60).tolist(),
            "volume": np.linspace(1000000, 2000000, 60).tolist(),
            "amount": np.linspace(100000000, 300000000, 60).tolist(),
            "amplitude": np.linspace(2, 4, 60).tolist(),
            "change_rate": np.linspace(0.1, 0.5, 60).tolist(),
            "turnover": np.linspace(1, 3, 60).tolist(),
            "ma5": np.linspace(100, 148, 56).tolist(),
            "ma10": np.linspace(100, 145, 51).tolist(),
            "ma20": np.linspace(100, 140, 41).tolist(),
            "ma60": [100] * 1,
            "atr14": np.linspace(1, 3, 47).tolist(),
            "net_amount_wan": np.linspace(100, 500, 60).tolist(),
            "total_amount_wan": np.linspace(1000, 5000, 60).tolist()
        }
    
    def test_rule_ma_crossover(self):
        """测试均线交叉规则"""
        # 构造金叉数据 - 直接修改close和volume，让计算出的MA5和MA20形成金叉
        data = self.test_data.copy()
        
        # 构造收盘价数据，使得MA5上穿MA20
        # 前半部分收盘价较低，后半部分收盘价较高
        close = np.array(data["close"])
        # 后半部分收盘价显著提高，确保MA5上穿MA20
        close[-20:] = np.linspace(140, 160, 20)
        data["close"] = close.tolist()
        
        # 构造成交量数据，确保足够大
        volume = np.array(data["volume"])
        volume[-1] = 3000000  # 当日成交量
        data["volume"] = volume.tolist()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_ma_crossover(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_trendline_breakout(self):
        """测试趋势线突破规则"""
        # 构造趋势线突破数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_trendline_breakout(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_dow_theory(self):
        """测试道氏理论规则"""
        # 构造道氏理论数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_dow_theory(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_macd_divergence(self):
        """测试MACD背离规则"""
        # 构造MACD背离数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_macd_divergence(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_bollinger_band_breakout(self):
        """测试布林带突破规则"""
        # 构造布林带突破数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_bollinger_band_breakout(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_quantile_regression(self):
        """测试分位数回归规则"""
        # 构造分位数回归数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_quantile_regression(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_volume_price_divergence(self):
        """测试量价背离规则"""
        # 构造量价背离数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_volume_price_divergence(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_obv_trend(self):
        """测试OBV趋势规则"""
        # 构造OBV趋势数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_obv_trend(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_capital_flow(self):
        """测试资金流规则"""
        # 构造资金流数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_capital_flow(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_turnover_trend(self):
        """测试换手率趋势规则"""
        # 构造换手率趋势数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_turnover_trend(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_atr_volatility(self):
        """测试ATR波动率规则"""
        # 构造ATR波动率数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_atr_volatility(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_volatility_expansion(self):
        """测试波动率收敛-发散规则"""
        # 构造波动率收敛-发散数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_volatility_expansion(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_rule_amplitude_trend(self):
        """测试振幅趋势规则"""
        # 构造振幅趋势数据
        data = self.test_data.copy()
        
        # 执行测试
        triggered, details = self.rule_engine.rule_amplitude_trend(data)
        
        # 验证结果结构
        self.assertIsInstance(triggered, bool)
        self.assertIsInstance(details, dict)
    
    def test_scan_stock(self):
        """测试扫描单个股票"""
        # 执行测试
        result = self.rule_engine.scan_stock("600000", self.test_data)
        
        # 验证结果结构
        self.assertIn("stock_code", result)
        self.assertIn("triggered_rules", result)
        self.assertIn("total_triggers", result)
        self.assertEqual(result["stock_code"], "600000")


if __name__ == "__main__":
    unittest.main()
