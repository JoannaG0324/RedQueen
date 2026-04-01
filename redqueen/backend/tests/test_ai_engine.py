import unittest
from unittest.mock import Mock, patch
from src.engine.ai_engine import AIEngine


class TestAIEngine(unittest.TestCase):
    """AI引擎单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.ai_engine = AIEngine()
    
    @patch('src.engine.ai_engine.requests.post')
    def test_call_doubao_api_success(self, mock_post):
        """测试调用豆包API成功"""
        # 模拟API响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "测试响应"
                        }
                    ]
                }
            ]
        }
        mock_post.return_value = mock_response
        
        # 执行测试
        result = self.ai_engine.call_doubao_api("测试提示词")
        
        # 验证结果
        self.assertIsNotNone(result)
        self.assertIn("output", result)
    
    @patch('src.engine.ai_engine.requests.post')
    def test_call_doubao_api_failure(self, mock_post):
        """测试调用豆包API失败"""
        # 模拟API响应失败
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        # 执行测试
        result = self.ai_engine.call_doubao_api("测试提示词")
        
        # 验证结果
        self.assertIsNone(result)
    
    @patch('src.engine.ai_engine.AIEngine.call_doubao_api')
    def test_map_stock_to_industry(self, mock_call_api):
        """测试个股-行业映射"""
        # 模拟API响应
        mock_call_api.return_value = {
            "output": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"stock_code": "600000", "stock_name": "浦发银行", "industry": "银行", "industry_code": "601", "confidence": 0.95}'
                        }
                    ]
                }
            ]
        }
        
        # 执行测试
        result = self.ai_engine.map_stock_to_industry("600000", "浦发银行")
        
        # 验证结果
        self.assertIsNotNone(result)
        self.assertEqual(result["stock_code"], "600000")
        self.assertEqual(result["industry"], "银行")
    
    @patch('src.engine.ai_engine.AIEngine.call_doubao_api')
    def test_get_industry_risk(self, mock_call_api):
        """测试行业风险探查"""
        # 模拟API响应
        mock_call_api.return_value = {
            "output": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "# 行业风险分析\n## 基础信息\n- 输入值：银行\n- 行业名称：银行\n- 分析周期：2024-01-01 至 2024-01-07\n\n## 行业共性风险\n1. 政策风险：监管趋严 - 来源：央行报告 2024-01-05\n2. 信用风险：不良贷款率上升 - 来源：银保监会 2024-01-03"
                        }
                    ]
                }
            ]
        }
        
        # 执行测试
        result = self.ai_engine.get_industry_risk("银行", "2024-01-07")
        
        # 验证结果
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "银行")
        self.assertIn("行业风险分析", result["risk_analysis"])
    
    @patch('src.engine.ai_engine.AIEngine.map_stock_to_industry')
    def test_batch_map_stocks_to_industries(self, mock_map):
        """测试批量映射个股到行业"""
        # 模拟映射结果
        mock_map.side_effect = [
            {"stock_code": "600000", "stock_name": "浦发银行", "industry": "银行"},
            {"stock_code": "600519", "stock_name": "贵州茅台", "industry": "白酒"}
        ]
        
        # 执行测试
        stocks = [
            {"stock_code": "600000", "stock_name": "浦发银行"},
            {"stock_code": "600519", "stock_name": "贵州茅台"}
        ]
        result = self.ai_engine.batch_map_stocks_to_industries(stocks)
        
        # 验证结果
        self.assertIn("600000", result)
        self.assertIn("600519", result)
        self.assertEqual(result["600000"]["industry"], "银行")
        self.assertEqual(result["600519"]["industry"], "白酒")
    
    @patch('src.engine.ai_engine.AIEngine.get_industry_risk')
    def test_batch_get_industry_risks(self, mock_get_risk):
        """测试批量获取行业风险"""
        # 模拟风险分析结果
        mock_get_risk.side_effect = [
            {"industry": "银行", "risk_analysis": "银行行业风险分析"},
            {"industry": "白酒", "risk_analysis": "白酒行业风险分析"}
        ]
        
        # 执行测试
        industries = ["银行", "白酒", "银行"]  # 重复行业
        result = self.ai_engine.batch_get_industry_risks(industries, "2024-01-07")
        
        # 验证结果
        self.assertIn("银行", result)
        self.assertIn("白酒", result)
        self.assertEqual(len(result), 2)  # 去重后只有2个行业


if __name__ == "__main__":
    unittest.main()
