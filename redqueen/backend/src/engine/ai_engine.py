import time
import json
import requests
from typing import Dict, Any, Optional
from src.utils.config import settings


class AIEngine:
    """AI双能力引擎模块"""
    
    def __init__(self):
        """初始化AI引擎"""
        self.api_key = settings.DOUBAO_API_KEY
        self.api_endpoint = settings.DOUBAO_API_ENDPOINT
        self.max_retries = 3
        self.timeout = 30
    
    def call_doubao_api(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用豆包大模型API"""
        headers = {
            "api key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "doubao-seed-2-0-pro-260215",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_endpoint,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result
                else:
                    print(f"API调用失败 (尝试 {attempt+1}/{self.max_retries}): {response.status_code} - {response.text}")
            except Exception as e:
                print(f"API调用异常 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")
            
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        return None
    
    def map_stock_to_industry(self, stock_code: str, stock_name: str) -> Optional[Dict[str, Any]]:
        """AI个股-行业映射"""
        prompt = f"请将股票代码 {stock_code}（股票名称：{stock_name}）映射到其所属的行业。输出格式为JSON，包含以下字段：\n"
        prompt += "{\n"
        prompt += "  \"stock_code\": \"股票代码\",\n"
        prompt += "  \"stock_name\": \"股票名称\",\n"
        prompt += "  \"industry\": \"所属行业名称\",\n"
        prompt += "  \"industry_code\": \"行业代码（如果有）\",\n"
        prompt += "  \"confidence\": \"置信度（0-1之间的数字）\"\n"
        prompt += "}\n"
        prompt += "请严格按照上述JSON格式输出，不要包含任何其他内容。"
        
        result = self.call_doubao_api(prompt)
        
        if result and "output" in result:
            try:
                # 解析API返回的结果
                output = result["output"][0]["content"][0]["text"]
                # 提取JSON部分
                import re
                json_match = re.search(r'\{[\s\S]*\}', output)
                if json_match:
                    json_str = json_match.group(0)
                    mapped_result = json.loads(json_str)
                    return mapped_result
            except Exception as e:
                print(f"解析个股-行业映射结果失败: {str(e)}")
        
        return None
    
    def get_industry_risk(self, industry: str, analyze_date: str) -> Optional[Dict[str, Any]]:
        """AI行业共性风险探查"""
        prompt = f"# AI行业共性风险分析\n"
        prompt += f"## 一、自动识别规则\n"
        prompt += f"1. 系统传入参数：\n"
        prompt += f"   - 目标对象：{industry}\n"
        prompt += f"   - 分析基准日期：{analyze_date}\n"
        prompt += "2. 自动计算时间窗口：基准日期前推7天\n"
        prompt += "3. 自动赛道判定：直接使用行业名称\n"
        prompt += "\n"
        prompt += "## 二、数据源要求\n"
        prompt += "仅采用时间窗口内的权威公开信息：\n"
        prompt += "- 头部券商行业研报\n"
        prompt += "- 行业协会官方报告\n"
        prompt += "- 权威财经媒体\n"
        prompt += "- 大宗商品价格监测\n"
        prompt += "禁止使用过期信息、个股私人信息、内幕信息。\n"
        prompt += "\n"
        prompt += "## 三、分析规则\n"
        prompt += "1. 只输出【行业共性风险】，彻底剔除个股专属风险（商誉、减持、业绩、公告等）\n"
        prompt += "2. 风险维度必须包括：政策、需求、成本、价格、技术、外贸\n"
        prompt += "3. 每条风险必须标注来源+日期\n"
        prompt += "\n"
        prompt += "## 四、输出格式（严格遵循）\n"
        prompt += "1. 基础信息：输入值、行业名称、分析周期\n"
        prompt += "2. 行业共性风险列表（每条带信源）\n"
        prompt += "3. 纯Markdown、无多余内容"
        
        result = self.call_doubao_api(prompt)
        
        if result and "output" in result:
            try:
                # 解析API返回的结果
                output = result["output"][0]["content"][0]["text"]
                return {
                    "industry": industry,
                    "analyze_date": analyze_date,
                    "risk_analysis": output
                }
            except Exception as e:
                print(f"解析行业风险结果失败: {str(e)}")
        
        return None
    
    def batch_map_stocks_to_industries(self, stocks: list) -> Dict[str, Dict[str, Any]]:
        """批量映射个股到行业"""
        results = {}
        
        for stock in stocks:
            stock_code = stock.get("stock_code")
            stock_name = stock.get("stock_name")
            if stock_code and stock_name:
                result = self.map_stock_to_industry(stock_code, stock_name)
                if result:
                    results[stock_code] = result
                else:
                    results[stock_code] = {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "industry": "未知",
                        "industry_code": "",
                        "confidence": 0.0
                    }
        
        return results
    
    def batch_get_industry_risks(self, industries: list, analyze_date: str) -> Dict[str, Dict[str, Any]]:
        """批量获取行业风险"""
        results = {}
        
        # 去重，同一行业只调用一次
        unique_industries = list(set(industries))
        
        for industry in unique_industries:
            result = self.get_industry_risk(industry, analyze_date)
            if result:
                results[industry] = result
        
        return results
