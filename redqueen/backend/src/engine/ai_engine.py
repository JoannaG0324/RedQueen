import time
import json
import requests
from typing import Dict, Any, Optional
from src.utils.config import settings
from src.utils.prompts import OPPORTUNITY_ANALYSIS_PROMPT, INDUSTRY_RISK_ANALYSIS_PROMPT, INDUSTRY_MAPPING_PROMPT


class AIEngine:
    """AI双能力引擎模块"""
    
    def __init__(self):
        """初始化AI引擎"""
        self.api_key = settings.DOUBAO_API_KEY
        self.api_endpoint = settings.DOUBAO_API_ENDPOINT
        self.max_retries = 3
        self.timeout = 60
    
    def call_doubao_api(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用豆包大模型API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 使用与API期望的标准请求形式一致的payload
        payload = {
            "model": "doubao-seed-2-0-pro-260215",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        print("\n=== AI模型交互开始 ===")
        print(f"API端点: {self.api_endpoint}")
        print(f"API Key: {self.api_key}")
        print(f"请求头: {headers}")
        print(f"请求体: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        
        for attempt in range(self.max_retries):
            try:
                print(f"\n尝试调用API (尝试 {attempt+1}/{self.max_retries})...")
                # 增加超时时间，确保API有足够的时间响应
                response = requests.post(
                    self.api_endpoint,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=60  # 增加超时时间到60秒
                )
                
                print(f"API响应状态码: {response.status_code}")
                print(f"API响应内容: {response.text}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"API响应解析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    print("=== AI模型交互结束 ===")
                    return result
                else:
                    print(f"API调用失败 (尝试 {attempt+1}/{self.max_retries}): {response.status_code} - {response.text}")
            except Exception as e:
                print(f"API调用异常 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")
            
            if attempt < self.max_retries - 1:
                print(f"等待 {2 ** attempt} 秒后重试...")
                time.sleep(2 ** attempt)  # 指数退避
        
        print("=== AI模型交互结束 (失败) ===")
        return None
    
    def map_stock_to_industry(self, stock_code: str, stock_name: str) -> Optional[Dict[str, Any]]:
        """AI个股-行业映射"""
        prompt = INDUSTRY_MAPPING_PROMPT.format(
            stock_code=stock_code,
            stock_name=stock_name
        )
        
        result = self.call_doubao_api(prompt)
        
        if result and "output" in result:
            try:
                # 打印API返回结果，以便调试
                print(f"API返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                
                # 解析API返回的结果（适配不同的返回结构）
                if isinstance(result["output"], list) and len(result["output"]) > 0:
                    output_item = result["output"][0]
                    # 尝试不同的路径
                    if "content" in output_item:
                        if isinstance(output_item["content"], list) and len(output_item["content"]) > 0:
                            content_item = output_item["content"][0]
                            if "text" in content_item:
                                output_text = content_item["text"]
                            elif "text" in output_item["content"]:
                                output_text = output_item["content"]["text"]
                            else:
                                output_text = str(output_item["content"])
                        elif isinstance(output_item["content"], str):
                            output_text = output_item["content"]
                        else:
                            output_text = str(output_item["content"])
                    elif "text" in output_item:
                        output_text = output_item["text"]
                    else:
                        output_text = str(output_item)
                else:
                    output_text = str(result["output"])
                
                # 提取JSON部分
                import re
                json_match = re.search(r'\{[\s\S]*\}', output_text)
                if json_match:
                    json_str = json_match.group(0)
                    mapped_result = json.loads(json_str)
                    return mapped_result
            except Exception as e:
                print(f"解析个股-行业映射结果失败: {str(e)}")
                print(f"API返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        return None
    
    def get_industry_risk(self, target_input: str, analyze_date: str) -> Optional[Dict[str, Any]]:
        """AI行业共性风险探查"""
        prompt = INDUSTRY_RISK_ANALYSIS_PROMPT.format(
            target_input=target_input,
            analyze_date=analyze_date
        )
        
        result = self.call_doubao_api(prompt)
        
        if result:
            try:
                # 打印API返回结果，以便调试
                print(f"API返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                
                # 解析API返回的结果（适配不同的返回结构）
                output_text = ""
                
                # 适配新的 API 端点返回格式
                if "choices" in result and isinstance(result["choices"], list):
                    for choice in result["choices"]:
                        if "message" in choice and "content" in choice["message"]:
                            output_text = choice["message"]["content"]
                            break
                # 适配旧的 API 端点返回格式
                elif "output" in result and isinstance(result["output"], list):
                    # 查找 type=message 的部分
                    message_item = None
                    for item in result["output"]:
                        if item.get("type") == "message":
                            message_item = item
                            break
                    
                    if message_item:
                        # 处理 message 类型的结果
                        if "content" in message_item and isinstance(message_item["content"], list):
                            for content_item in message_item["content"]:
                                if content_item.get("type") == "output_text" and "text" in content_item:
                                    output_text = content_item["text"]
                                    break
                    else:
                        # 没有找到 message 类型的结果，使用第一个结果
                        output_item = result["output"][0]
                        # 尝试不同的路径
                        if "content" in output_item:
                            if isinstance(output_item["content"], list) and len(output_item["content"]) > 0:
                                content_item = output_item["content"][0]
                                if "text" in content_item:
                                    output_text = content_item["text"]
                                elif "text" in output_item["content"]:
                                    output_text = output_item["content"]["text"]
                                else:
                                    output_text = str(output_item["content"])
                            elif isinstance(output_item["content"], str):
                                output_text = output_item["content"]
                            else:
                                output_text = str(output_item["content"])
                        elif "text" in output_item:
                            output_text = output_item["text"]
                        else:
                            output_text = str(output_item)
                else:
                    output_text = str(result)
                
                return {
                    "industry": target_input,
                    "analyze_date": analyze_date,
                    "risk_analysis": output_text
                }
            except Exception as e:
                print(f"解析行业风险结果失败: {str(e)}")
                print(f"API返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
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
    
    def batch_get_industry_risks(self, target_inputs: list, analyze_date: str) -> Dict[str, Dict[str, Any]]:
        """批量获取行业风险"""
        results = {}
        
        # 去重，同一目标对象只调用一次
        unique_targets = list(set(target_inputs))
        
        for target in unique_targets:
            result = self.get_industry_risk(target, analyze_date)
            if result:
                results[target] = result
        
        return results
