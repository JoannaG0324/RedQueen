from sqlalchemy import Column, Integer, String, Date, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import enum

from src.utils.database import Base


class TaskStatus(enum.Enum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnomalyStock(Base):
    """异动个股表"""
    __tablename__ = "rq_anomaly_stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    scan_date = Column(Date, nullable=False, index=True)
    target_date = Column(Date, nullable=False, index=True)
    total_triggers = Column(Integer, nullable=False)
    triggered_rules = Column(JSON, nullable=False)
    industry = Column(String(50))
    industry_code = Column(String(20))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class IndustryRisk(Base):
    """行业风险表"""
    __tablename__ = "rq_industry_risks"
    
    id = Column(Integer, primary_key=True, index=True)
    industry = Column(String(50), nullable=False, index=True)
    analyze_date = Column(Date, nullable=False, index=True)
    risk_analysis = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ScanTask(Base):
    """扫描任务表"""
    __tablename__ = "rq_scan_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(50), nullable=False, unique=True, index=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, index=True)
    start_time = Column(DateTime, default=func.now())
    end_time = Column(DateTime, nullable=True)
    total_stocks = Column(Integer, default=0)
    processed_stocks = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class PersistenceManager:
    """数据持久化管理类"""
    
    def __init__(self, db: Session):
        """初始化持久化管理器"""
        self.db = db
    
    def save_anomaly_stock(self, stock_data: Dict[str, Any]) -> AnomalyStock:
        """保存异动个股数据"""
        stock = AnomalyStock(**stock_data)
        self.db.add(stock)
        self.db.commit()
        self.db.refresh(stock)
        return stock
    
    def save_batch_anomaly_stocks(self, stocks_data: List[Dict[str, Any]]) -> List[AnomalyStock]:
        """批量保存异动个股数据"""
        if not stocks_data:
            return []
        
        # 获取目标日期
        target_date = stocks_data[0].get('target_date')
        
        # 删除该目标日期的所有数据，确保一天只保留一次扫描数据
        if target_date:
            self.db.query(AnomalyStock).filter(AnomalyStock.target_date == target_date).delete()
        
        # 插入新数据
        stocks = [AnomalyStock(**data) for data in stocks_data]
        self.db.add_all(stocks)
        self.db.commit()
        return stocks
    
    def get_anomaly_stocks_by_date(self, target_date: Date) -> List[AnomalyStock]:
        """按目标日期获取异动个股"""
        return self.db.query(AnomalyStock).filter(AnomalyStock.target_date == target_date).order_by(AnomalyStock.total_triggers.desc()).all()
    
    def get_anomaly_stock_by_code_and_date(self, stock_code: str, target_date: Date) -> Optional[AnomalyStock]:
        """按股票代码和目标日期获取异动个股"""
        return self.db.query(AnomalyStock).filter(
            AnomalyStock.stock_code == stock_code,
            AnomalyStock.target_date == target_date
        ).first()
    
    def get_anomaly_stocks_by_date_range(self, start_date: Date, end_date: Date) -> List[AnomalyStock]:
        """按日期范围获取异动个股"""
        return self.db.query(AnomalyStock).filter(
            AnomalyStock.target_date >= start_date,
            AnomalyStock.target_date <= end_date
        ).all()
    
    def save_industry_risk(self, risk_data: Dict[str, Any]) -> IndustryRisk:
        """保存行业风险数据"""
        # 检查是否已存在相同行业和日期的风险数据
        existing = self.db.query(IndustryRisk).filter(
            IndustryRisk.industry == risk_data.get("industry"),
            IndustryRisk.analyze_date == risk_data.get("analyze_date")
        ).first()
        
        if existing:
            # 更新现有数据
            existing.risk_analysis = risk_data.get("risk_analysis")
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # 创建新数据
            risk = IndustryRisk(**risk_data)
            self.db.add(risk)
            self.db.commit()
            self.db.refresh(risk)
            return risk
    
    def get_industry_risk(self, industry: str, analyze_date: Date) -> Optional[IndustryRisk]:
        """获取行业风险数据"""
        return self.db.query(IndustryRisk).filter(
            IndustryRisk.industry == industry,
            IndustryRisk.analyze_date == analyze_date
        ).first()
    
    def save_scan_task(self, task_data: Dict[str, Any]) -> ScanTask:
        """保存扫描任务"""
        task = ScanTask(**task_data)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def update_scan_task(self, task_id: str, update_data: Dict[str, Any]) -> Optional[ScanTask]:
        """更新扫描任务"""
        task = self.db.query(ScanTask).filter(ScanTask.task_id == task_id).first()
        if task:
            for key, value in update_data.items():
                setattr(task, key, value)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def get_scan_task(self, task_id: str) -> Optional[ScanTask]:
        """获取扫描任务"""
        return self.db.query(ScanTask).filter(ScanTask.task_id == task_id).first()
    
    def get_scan_tasks_by_status(self, status: TaskStatus) -> List[ScanTask]:
        """按状态获取扫描任务"""
        return self.db.query(ScanTask).filter(ScanTask.status == status).all()
