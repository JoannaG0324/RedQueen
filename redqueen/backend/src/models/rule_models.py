from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from src.utils.database import Base


class TriggeredRule(Base):
    """规则信息表"""
    __tablename__ = "rq_triggered_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(100), nullable=False, unique=True, index=True)
    rule_detail = Column(Text, nullable=False)
    rule_chinese_name = Column(String(100), nullable=False)
    status = Column(Integer, default=0, nullable=False)  # 0: 关闭, 1: 开启
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class RuleManager:
    """规则管理类"""
    
    def __init__(self, db: Session):
        """初始化规则管理器"""
        self.db = db
    
    def get_all_rules(self) -> List[TriggeredRule]:
        """获取所有规则"""
        return self.db.query(TriggeredRule).all()
    
    def get_enabled_rules(self) -> List[TriggeredRule]:
        """获取启用的规则"""
        return self.db.query(TriggeredRule).filter(TriggeredRule.status == 1).all()
    
    def get_rule_by_name(self, rule_name: str) -> Optional[TriggeredRule]:
        """根据规则名称获取规则"""
        return self.db.query(TriggeredRule).filter(TriggeredRule.rule_name == rule_name).first()
    
    def create_rule(self, rule_data: Dict[str, Any]) -> TriggeredRule:
        """创建规则"""
        rule = TriggeredRule(**rule_data)
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule
    
    def update_rule_status(self, rule_name: str, status: int) -> Optional[TriggeredRule]:
        """更新规则状态"""
        rule = self.get_rule_by_name(rule_name)
        if rule:
            rule.status = status
            rule.updated_at = func.now()
            self.db.commit()
            self.db.refresh(rule)
        return rule
    
    def initialize_default_rules(self):
        """初始化默认规则"""
        default_rules = [
            {
                "rule_name": "rule_ma_crossover",
                "rule_detail": "MA5上穿MA20，量能大于20日均量的1.2倍，连续2日收盘价大于MA20",
                "rule_chinese_name": "均线交叉趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_trendline_breakout",
                "rule_detail": "最近30日低点拟合上升趋势线，收盘价突破趋势线1%以上，连续2日不跌破趋势线",
                "rule_chinese_name": "趋势线突破异动",
                "status": 1
            },
            {
                "rule_name": "rule_dow_theory",
                "rule_detail": "识别最近60日高低点，出现更高低点和更高高点",
                "rule_chinese_name": "道氏高低点趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_macd_divergence",
                "rule_detail": "MACD底背离，价格创新低但DIF未创新低，同时出现金叉",
                "rule_chinese_name": "MACD趋势背离异动",
                "status": 1
            },
            {
                "rule_name": "rule_bollinger_band_breakout",
                "rule_detail": "布林带带宽收敛至20%分位以下，向上突破上轨，持续2日",
                "rule_chinese_name": "布林带通道突破异动",
                "status": 1
            },
            {
                "rule_name": "rule_quantile_regression",
                "rule_detail": "收益率斜率由负变正，斜率变化大于0.001",
                "rule_chinese_name": "分位数回归趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_volume_price_divergence",
                "rule_detail": "价格创新低但成交量未创新低，3日内收阳",
                "rule_chinese_name": "量价背离趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_obv_trend",
                "rule_detail": "OBV创新高但价格未创新高，OBV上穿20日均线",
                "rule_chinese_name": "OBV能量潮趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_capital_flow",
                "rule_detail": "5日累计净流入占比≥5%，连续3日资金为正",
                "rule_chinese_name": "主力资金流趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_turnover_trend",
                "rule_detail": "当日换手率≥2倍20日均量，股价处于相对低位，当日收涨，持续2日",
                "rule_chinese_name": "换手率趋势异动",
                "status": 1
            },
            {
                "rule_name": "rule_atr_volatility",
                "rule_detail": "ATR从10%历史分位上升幅度≥50%，3日内收盘价持续上行",
                "rule_chinese_name": "ATR波动率异动",
                "status": 1
            },
            {
                "rule_name": "rule_volatility_expansion",
                "rule_detail": "波动率降至历史20%分位并持续10日，当日波动率≥2倍前值且收益率为正",
                "rule_chinese_name": "波动率收敛-发散异动",
                "status": 1
            },
            {
                "rule_name": "rule_amplitude_trend",
                "rule_detail": "当日振幅≥1.5倍20日均值，当日收涨，持续2日",
                "rule_chinese_name": "振幅异动趋势识别",
                "status": 1
            },
            {
                "rule_name": "rule_exposure_frequency",
                "rule_detail": "3日内出现超过2次异动规则命中或5日内出现超过3次异动规则命中",
                "rule_chinese_name": "暴露频率异动",
                "status": 1
            }
        ]
        
        for rule_data in default_rules:
            existing_rule = self.get_rule_by_name(rule_data["rule_name"])
            if not existing_rule:
                self.create_rule(rule_data)
