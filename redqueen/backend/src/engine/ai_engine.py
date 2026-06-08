import time
import json
import requests
from typing import Dict, Any, Optional
from src.utils.config import settings
from src.utils.prompts import OPPORTUNITY_ANALYSIS_PROMPT


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
