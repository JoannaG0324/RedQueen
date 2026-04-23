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
        # 获取基础行情数据（从最早日期到target_date）
        price_data = self.db.query(StockDailyQfq).filter(
            and_(
                StockDailyQfq.stock_code == stock_code,
                StockDailyQfq.date <= target_date
            )
        ).order_by(StockDailyQfq.date).all()
        
        if not price_data:
            return None
        
        # 获取技术指标数据（从最早日期到target_date）
        tech_data = self.db.query(StockDailyQfqCalc).filter(
            and_(
                StockDailyQfqCalc.stock_code == stock_code,
                StockDailyQfqCalc.date <= target_date
            )
        ).order_by(StockDailyQfqCalc.date).all()
        
        # 获取资金流向数据（从最早日期到target_date）
        flow_data = self.db.query(StockDailyFlow).filter(
            and_(
                StockDailyFlow.stock_code == stock_code,
                StockDailyFlow.date <= target_date
            )
        ).order_by(StockDailyFlow.date).all()
        
        # 数据清洗与标准化
        cleaned_data = self._clean_and_standardize_data(price_data, tech_data, flow_data)
        
        # 数据校验
        if not self._validate_data(cleaned_data, days):
            return None
        
        # 只返回最近的days天数据
        if len(cleaned_data["dates"]) > days:
            # 计算起始索引
            start_index = len(cleaned_data["dates"]) - days
            # 截断所有数据数组
            for key in cleaned_data:
                if isinstance(cleaned_data[key], list):
                    cleaned_data[key] = cleaned_data[key][start_index:]
        
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
        # 检查数据长度，使用合理的最小数据长度要求
        # 对于任何天数，要求至少有 20 天的数据
        min_days = min(20, max(10, int(days * 0.5)))
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
    
    def get_industry_data(self, target_date: date) -> List[Dict[str, Any]]:
        """获取行业数据"""
        try:
            from sqlalchemy import text
            # 使用用户提供的SQL查询获取实际数据
            query = """
            SELECT 
                f.date, 
                f.industry_name, 
                m.industry_code, 
                f.net_inflow, 
                f.up_count, 
                f.down_count, 
                f.change_percent, 
                i.close as close_price, 
                c.ma3, c.ma5, c.ma10, c.ma20, c.ma60 
            FROM industry_flow_ODS f 
            JOIN industry_ths m ON f.industry_name = m.industry_name 
            LEFT JOIN industry_ths_index i ON m.industry_code = i.industry_code AND i.date = f.date 
            LEFT JOIN industry_ths_index_calc c ON m.industry_code = c.industry_code AND c.date = f.date 
            WHERE f.date = :filter_date 
            ORDER BY f.net_inflow DESC
            """
            
            # 执行查询
            result = self.db.execute(text(query), {"filter_date": target_date})
            rows = result.fetchall()
            
            # 处理查询结果
            industry_data = []
            for row in rows:
                # 计算成分股数量
                count = row.up_count + row.down_count
                # 计算上涨比例
                up_pct = (row.up_count / count * 100) if count > 0 else 0
                # 计算偏离度
                dev_3 = ((row.close_price - row.ma3) / row.ma3 * 100) if row.ma3 and row.ma3 > 0 else 0
                dev_5 = ((row.close_price - row.ma5) / row.ma5 * 100) if row.ma5 and row.ma5 > 0 else 0
                dev_20 = ((row.close_price - row.ma20) / row.ma20 * 100) if row.ma20 and row.ma20 > 0 else 0
                dev_60 = ((row.close_price - row.ma60) / row.ma60 * 100) if row.ma60 and row.ma60 > 0 else 0
                
                industry_data.append({
                    "industry": row.industry_name,
                    "industry_code": row.industry_code,
                    "count": count,
                    "up_pct": round(up_pct, 2),
                    "net_inflow": float(round(row.net_inflow, 2)),
                    "change_percent": float(round(row.change_percent, 2)),
                    "dev_3": round(dev_3, 2),
                    "dev_5": round(dev_5, 2),
                    "dev_20": round(dev_20, 2),
                    "dev_60": round(dev_60, 2)
                })
            
            return industry_data
        except Exception as e:
            print(f"获取行业数据失败: {str(e)}")
            raise
    
    def get_industry_kline_data(self, industry_code: str, days: int, end_date: date) -> List[Dict[str, Any]]:
        """获取行业K线数据"""
        try:
            from sqlalchemy import text
            # 查询行业K线数据，获取从最早日期到end_date的所有数据
            query = """
            SELECT 
                date, 
                open, 
                close, 
                high, 
                low, 
                volume, 
                amount 
            FROM industry_ths_index 
            WHERE industry_code = :industry_code 
            AND date <= :end_date 
            ORDER BY date
            """
            
            # 执行查询
            result = self.db.execute(text(query), {
                "industry_code": industry_code,
                "end_date": end_date
            })
            rows = result.fetchall()
            
            # 处理查询结果
            kline_data = []
            close_prices = []
            
            for row in rows:
                kline_data.append({
                    "date": row.date.isoformat(),
                    "open": row.open,
                    "close": row.close,
                    "high": row.high,
                    "low": row.low,
                    "volume": row.volume,
                    "amount": row.amount,
                    "ma5": None,
                    "ma10": None,
                    "ma20": None,
                    "ma60": None
                })
                close_prices.append(row.close)
            
            # 计算MA值
            for i in range(len(kline_data)):
                # 计算MA5：只在有至少5个数据点时计算
                if i >= 4:
                    kline_data[i]["ma5"] = sum(close_prices[i-4:i+1]) / 5
                # 计算MA10：只在有至少10个数据点时计算
                if i >= 9:
                    kline_data[i]["ma10"] = sum(close_prices[i-9:i+1]) / 10
                # 计算MA20：只在有至少20个数据点时计算
                if i >= 19:
                    kline_data[i]["ma20"] = sum(close_prices[i-19:i+1]) / 20
                # 计算MA60：只在有至少60个数据点时计算
                if i >= 59:
                    kline_data[i]["ma60"] = sum(close_prices[i-59:i+1]) / 60
            
            # 只返回最近的days天数据
            if len(kline_data) > days:
                kline_data = kline_data[-days:]
            
            return kline_data
        except Exception as e:
            print(f"获取行业K线数据失败: {str(e)}")
            raise

