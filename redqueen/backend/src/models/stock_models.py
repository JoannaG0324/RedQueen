from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, DECIMAL
from sqlalchemy.sql import func

from src.utils.database import Base


class StockDailyQfq(Base):
    """股票前复权日线行情表（原始备份，只读保留）"""
    __tablename__ = "stock_daily_qfq"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(Text)
    date = Column(Date)
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    amplitude = Column(Float)
    change_rate = Column(Float)
    change_amount = Column(Float)
    turnover = Column(Float)
    stock_name = Column(Text)


class StockDailyAnalysis(Base):
    """股票前复权日线行情表（最终使用量价数据，页面与计算默认读该表）"""
    __tablename__ = "stock_daily_analysis"

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(Text)
    date = Column(Date)
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    amplitude = Column(Float)
    change_rate = Column(Float)
    change_amount = Column(Float)
    turnover = Column(Float)
    stock_name = Column(Text)


class StockDailyQfqCalc(Base):
    """股票技术指标计算表"""
    __tablename__ = "stock_daily_qfq_calc"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20))
    date = Column(Date)
    ma3 = Column(Float)
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    ma30 = Column(Float)
    ma60 = Column(Float)
    ma90 = Column(Float)
    ma120 = Column(Float)
    ma200 = Column(Float)
    atr3 = Column(Float)
    atr5 = Column(Float)
    atr10 = Column(Float)
    atr14 = Column(Float)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    growth_streak_days = Column(DECIMAL(5, 1))
    growth_streak_pct = Column(DECIMAL(10, 4))


class StockDailyFlow(Base):
    """股票每日资金流向数据"""
    __tablename__ = "stock_daily_flow"
    
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(Integer)
    stock_code = Column(String(10), index=True)
    stock_name = Column(String(50))
    close = Column(DECIMAL(10, 2))
    change_rate = Column(DECIMAL(10, 4))
    turnover = Column(DECIMAL(10, 2))
    inflow_amount = Column(String(50))
    outflow_amount = Column(String(50))
    net_amount = Column(String(50))
    total_amount = Column(String(50))
    inflow_amount_wan = Column(DECIMAL(15, 2))
    outflow_amount_wan = Column(DECIMAL(15, 2))
    net_amount_wan = Column(DECIMAL(15, 2))
    total_amount_wan = Column(DECIMAL(15, 2))
    date = Column(Date, index=True)


class StockInfo(Base):
    """股票基础信息表"""
    __tablename__ = "stock_info"
    
    stock_code = Column(Text, primary_key=True)
    stock_name = Column(Text)
    ipo_date = Column(Text)
    market = Column(Text)


class IndustryThs(Base):
    """同花顺行业分类表"""
    __tablename__ = "industry_ths"
    
    id = Column(Integer, primary_key=True, index=True)
    industry_code = Column(Text, unique=True, index=True)
    industry_name = Column(Text)
    edit_date = Column(Date)
    flag = Column(Integer, default=1)


class IndustryThsStock(Base):
    """个股对应同花顺行业表"""
    __tablename__ = "industry_ths_stock"
    
    stock_code = Column(Text, primary_key=True)
    stock_name = Column(Text)
    industry_code = Column(Text, index=True)
    edit_date = Column(Date)


class StockFavorite(Base):
    """股票收藏表 - 用户关注的股票"""
    __tablename__ = "stock_favorite"

    stock_code = Column(String(20), primary_key=True, nullable=False, index=True)
    price_date = Column(Date, nullable=False)
    status = Column(Integer, nullable=False, default=1)
    tag = Column(String(20), nullable=True, default=None)
    updated_time = Column(DateTime, nullable=False, server_default=func.now())
