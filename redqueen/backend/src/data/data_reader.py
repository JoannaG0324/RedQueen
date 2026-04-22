from typing import List, Dict, Optional, Any
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from src.models.stock_models import StockDailyQfq, StockDailyQfqCalc, StockDailyFlow, StockInfo, IndustryThs, IndustryThsStock


class DataReader:
    """数据读取与预处理模块"""
    
    def __init__(self, db: Session):
        """初始化数据读取器"""
        self.db = db
    
    def get_stock_list(self) -> List[Dict[str, str]]:
        """获取股票列表"""
        stocks = self.db.query(StockInfo.stock_code, StockInfo.stock_name).all()
        return [{
            "stock_code": stock.stock_code,
            "stock_name": stock.stock_name
        } for stock in stocks]
    
    def get_stock_data_by_date(self, stock_code: str, target_date: date, days: int = 60) -> Optional[Dict[str, Any]]:
        """获取指定股票在指定日期的历史数据"""
        # 计算起始日期
        start_date = target_date - timedelta(days=days)
        
        # 获取基础行情数据
        price_data = self.db.query(StockDailyQfq).filter(
            and_(
                StockDailyQfq.stock_code == stock_code,
                StockDailyQfq.date >= start_date,
                StockDailyQfq.date <= target_date
            )
        ).order_by(StockDailyQfq.date).all()
        
        if not price_data:
            return None
        
        # 获取技术指标数据
        tech_data = self.db.query(StockDailyQfqCalc).filter(
            and_(
                StockDailyQfqCalc.stock_code == stock_code,
                StockDailyQfqCalc.date >= start_date,
                StockDailyQfqCalc.date <= target_date
            )
        ).order_by(StockDailyQfqCalc.date).all()
        
        # 获取资金流向数据
        flow_data = self.db.query(StockDailyFlow).filter(
            and_(
                StockDailyFlow.stock_code == stock_code,
                StockDailyFlow.date >= start_date,
                StockDailyFlow.date <= target_date
            )
        ).order_by(StockDailyFlow.date).all()
        
        # 数据清洗与标准化
        cleaned_data = self._clean_and_standardize_data(price_data, tech_data, flow_data)
        
        # 数据校验
        if not self._validate_data(cleaned_data, days):
            return None
        
        return cleaned_data
    
    def get_batch_stock_data(self, stock_codes: List[str], target_date: date, days: int = 60) -> Dict[str, Dict[str, Any]]:
        """批量获取股票数据"""
        result = {}
        for stock_code in stock_codes:
            data = self.get_stock_data_by_date(stock_code, target_date, days)
            if data:
                result[stock_code] = data
        return result
    
    def _clean_and_standardize_data(self, price_data: List, tech_data: List, flow_data: List) -> Dict[str, Any]:
        """数据清洗与标准化"""
        # 构建日期索引的数据结构
        price_dict = {item.date: item for item in price_data}
        tech_dict = {item.date: item for item in tech_data}
        flow_dict = {item.date: item for item in flow_data}
        
        # 统一日期范围
        all_dates = sorted(list(set(price_dict.keys()) | set(tech_dict.keys()) | set(flow_dict.keys())))
        
        # 构建标准化数据
        standardized_data = {
            "dates": [d.isoformat() for d in all_dates],
            "open": [],
            "close": [],
            "high": [],
            "low": [],
            "volume": [],
            "amount": [],
            "amplitude": [],
            "change_rate": [],
            "turnover": [],
            "ma5": [],
            "ma10": [],
            "ma20": [],
            "ma60": [],
            "atr14": [],
            "net_amount_wan": [],
            "total_amount_wan": []
        }
        
        for d in all_dates:
            # 价格数据
            price = price_dict.get(d)
            standardized_data["open"].append(price.open if price else None)
            standardized_data["close"].append(price.close if price else None)
            standardized_data["high"].append(price.high if price else None)
            standardized_data["low"].append(price.low if price else None)
            standardized_data["volume"].append(price.volume if price else None)
            standardized_data["amount"].append(price.amount if price else None)
            standardized_data["amplitude"].append(price.amplitude if price else None)
            standardized_data["change_rate"].append(price.change_rate if price else None)
            standardized_data["turnover"].append(price.turnover if price else None)
            
            # 技术指标数据
            tech = tech_dict.get(d)
            standardized_data["ma5"].append(tech.ma5 if tech else None)
            standardized_data["ma10"].append(tech.ma10 if tech else None)
            standardized_data["ma20"].append(tech.ma20 if tech else None)
            standardized_data["ma60"].append(tech.ma60 if tech else None)
            standardized_data["atr14"].append(tech.atr14 if tech else None)
            
            # 资金流向数据
            flow = flow_dict.get(d)
            standardized_data["net_amount_wan"].append(flow.net_amount_wan if flow else None)
            standardized_data["total_amount_wan"].append(flow.total_amount_wan if flow else None)
        
        # 填充缺失值（简单的前向填充）
        for key in standardized_data:
            if key != "dates":
                for i in range(1, len(standardized_data[key])):
                    if standardized_data[key][i] is None and standardized_data[key][i-1] is not None:
                        standardized_data[key][i] = standardized_data[key][i-1]
        
        return standardized_data
    
    def _validate_data(self, data: Dict[str, Any], days: int = 60) -> bool:
        """数据校验"""
        # 检查数据长度，根据传入的 days 参数动态调整
        # 对于短期数据（如 20 天），要求至少有 10 天的数据
        min_days = max(10, int(days * 0.5))
        if len(data["dates"]) < min_days:
            return False
        
        # 检查关键指标是否有足够的数据
        for key in ["close", "volume"]:
            valid_count = sum(1 for x in data[key] if x is not None)
            if valid_count < len(data[key]) * 0.6:
                return False
        
        return True
    
    def get_stock_industry(self, stock_code: str) -> Dict[str, str]:
        """获取股票对应的同花顺行业信息"""
        # 查询个股对应的行业
        industry_stock = self.db.query(IndustryThsStock).filter(IndustryThsStock.stock_code == stock_code).first()
        
        if not industry_stock:
            return {"industry": None, "industry_code": None}
        
        # 查询行业名称
        industry = self.db.query(IndustryThs).filter(IndustryThs.industry_code == industry_stock.industry_code).first()
        
        if not industry:
            return {"industry": None, "industry_code": industry_stock.industry_code}
        
        return {"industry": industry.industry_name, "industry_code": industry.industry_code}
    
    def is_trading_day(self, target_date: date) -> bool:
        """检查指定日期是否为交易日"""
        # 查询 StockDailyQfq 表中是否有 target_date 的数据
        count = self.db.query(StockDailyQfq).filter(StockDailyQfq.date == target_date).count()
        return count > 0
