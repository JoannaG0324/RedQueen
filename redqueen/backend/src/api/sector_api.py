from typing import List, Dict, Any
import requests
import re


def fetch_stock_sectors(stock_code: str) -> List[Dict[str, Any]]:
    """
    获取个股所属板块信息
    
    数据源：搜狐股票行情 API
    接口格式：https://hq.stock.sohu.com/cn/{code_suffix}/cn_{stock_code}-1.html
    
    返回数据结构：
    [{
        "code": str,        # 板块代码
        "name": str,        # 板块名称
        "change_rate": str  # 板块涨跌幅（如 "1.05%"）
    }]
    """
    try:
        code_suffix = stock_code[-3:]
        url = f"https://hq.stock.sohu.com/cn/{code_suffix}/cn_{stock_code}-1.html"
        
        response = requests.get(url, timeout=5)
        response.encoding = 'gbk'
        content = response.text
        
        sector_match = re.search(r"'sector':(\[\[.*?\]\])", content, re.S)
        if not sector_match:
            return []
        
        sector_str = sector_match.group(1)
        sector_str = sector_str.replace("'", "\"")
        
        import json
        sectors = json.loads(sector_str)
        
        result = []
        for sector in sectors:
            if len(sector) >= 3:
                result.append({
                    "code": sector[0],
                    "name": sector[1],
                    "change_rate": sector[2]
                })
        
        return result
    
    except Exception as e:
        return []
