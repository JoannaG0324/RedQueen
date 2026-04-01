from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import date, datetime
import uuid
import csv
import io
from typing import List, Dict, Any

from src.utils.database import get_db, Base, engine

# 导入所有模型类，确保创建数据库表时包含所有表结构
from src.models.persistence_models import PersistenceManager, TaskStatus
from src.models.rule_models import RuleManager, TriggeredRule

# 删除现有表并重新创建
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
from src.data.data_reader import DataReader
from src.engine.rule_engine import RuleEngine
from src.engine.ai_engine import AIEngine

# 初始化规则表
from sqlalchemy.orm import Session
from src.utils.database import SessionLocal
db = SessionLocal()
try:
    rule_manager = RuleManager(db)
    rule_manager.initialize_default_rules()
finally:
    db.close()

# 创建FastAPI应用
app = FastAPI(
    title="RedQueen投资助手API",
    description="RedQueen投资助手后端API接口",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局实例
rule_engine = RuleEngine()
ai_engine = AIEngine()


@app.post("/api/scan/trigger", response_model=Dict[str, Any])
async def trigger_scan(background_tasks: BackgroundTasks, target_date: str = None, db: Session = Depends(get_db)):
    """手动触发全市场扫描"""
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 创建扫描任务
    persistence_manager = PersistenceManager(db)
    task_data = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "total_stocks": 0,
        "processed_stocks": 0
    }
    persistence_manager.save_scan_task(task_data)
    
    # 后台执行扫描
    background_tasks.add_task(perform_scan, task_id, db, target_date)
    
    return {
        "task_id": task_id,
        "message": "扫描任务已启动"
    }


def perform_scan(task_id: str, db: Session, target_date_str: str = None):
    """执行扫描任务"""
    persistence_manager = PersistenceManager(db)
    data_reader = DataReader(db)
    rule_manager = RuleManager(db)
    
    try:
        # 更新任务状态为运行中
        persistence_manager.update_scan_task(task_id, {"status": TaskStatus.RUNNING})
        
        # 获取股票列表
        stocks = data_reader.get_stock_list()
        total_stocks = len(stocks)
        persistence_manager.update_scan_task(task_id, {"total_stocks": total_stocks})
        
        # 确定目标日期
        if target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
        
        # 批量获取股票数据
        stock_data_dict = data_reader.get_batch_stock_data(
            [stock["stock_code"] for stock in stocks],
            target_date
        )
        
        # 获取启用的规则及其中文名称
        enabled_rules = rule_manager.get_enabled_rules()
        enabled_rule_names = [rule.rule_name for rule in enabled_rules]
        
        # 创建规则名称到中文名称的映射
        rule_name_to_chinese = {rule.rule_name: rule.rule_chinese_name for rule in enabled_rules}
        
        # 批量扫描股票
        scan_results = rule_engine.batch_scan(stock_data_dict, enabled_rules=enabled_rule_names)
        
        # 提取异动个股
        anomaly_stocks = []
        
        for stock_code, result in scan_results.items():
            if result["total_triggers"] > 0:
                # 找到股票名称
                stock_name = next((s["stock_name"] for s in stocks if s["stock_code"] == stock_code), "未知")
                
                # 为每个触发的规则添加中文名称
                triggered_rules_with_chinese = []
                for rule in result["triggered_rules"]:
                    rule_with_chinese = rule.copy()
                    rule_with_chinese["rule_chinese_name"] = rule_name_to_chinese.get(rule["rule_name"], rule["rule_name"])
                    triggered_rules_with_chinese.append(rule_with_chinese)
                
                # 构建异动个股数据（暂时不进行行业映射）
                stock_data = {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "scan_date": date.today(),
                    "target_date": target_date,
                    "total_triggers": result["total_triggers"],
                    "triggered_rules": triggered_rules_with_chinese,
                    "industry": "未知",
                    "industry_code": ""
                }
                anomaly_stocks.append(stock_data)
            
            # 更新处理进度
            processed = len(anomaly_stocks)
            if processed % 100 == 0:
                persistence_manager.update_scan_task(task_id, {"processed_stocks": processed})
        
        # 批量保存异动个股
        if anomaly_stocks:
            persistence_manager.save_batch_anomaly_stocks(anomaly_stocks)
        
        # 更新任务状态为完成
        persistence_manager.update_scan_task(
            task_id,
            {
                "status": TaskStatus.COMPLETED,
                "end_time": datetime.now(),
                "processed_stocks": len(anomaly_stocks)
            }
        )
        
    except Exception as e:
        # 更新任务状态为失败
        persistence_manager.update_scan_task(
            task_id,
            {
                "status": TaskStatus.FAILED,
                "end_time": datetime.now(),
                "error_message": str(e)
            }
        )


@app.get("/api/scan/status/{task_id}", response_model=Dict[str, Any])
async def get_scan_status(task_id: str, db: Session = Depends(get_db)):
    """获取扫描任务状态"""
    persistence_manager = PersistenceManager(db)
    task = persistence_manager.get_scan_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "total_stocks": task.total_stocks,
        "processed_stocks": task.processed_stocks,
        "error_message": task.error_message
    }


@app.get("/api/anomaly/stocks", response_model=List[Dict[str, Any]])
async def get_anomaly_stocks(target_date: date, db: Session = Depends(get_db)):
    """获取异动个股列表"""
    persistence_manager = PersistenceManager(db)
    stocks = persistence_manager.get_anomaly_stocks_by_date(target_date)
    
    return [{
        "id": stock.id,
        "stock_code": stock.stock_code,
        "stock_name": stock.stock_name,
        "scan_date": stock.scan_date,
        "target_date": stock.target_date,
        "total_triggers": stock.total_triggers,
        "triggered_rules": stock.triggered_rules,
        "industry": stock.industry,
        "industry_code": stock.industry_code,
        "created_at": stock.created_at
    } for stock in stocks]


@app.get("/api/anomaly/stock/{stock_code}", response_model=Dict[str, Any])
async def get_anomaly_stock(stock_code: str, target_date: date, db: Session = Depends(get_db)):
    """获取异动个股详情"""
    persistence_manager = PersistenceManager(db)
    stock = persistence_manager.get_anomaly_stock_by_code_and_date(stock_code, target_date)
    
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    
    # 获取行业风险
    industry_risk = None
    if not stock.industry or stock.industry == "未知":
        # 调用AI进行个股-行业映射
        industry_result = ai_engine.map_stock_to_industry(stock_code, stock.stock_name)
        if industry_result:
            stock.industry = industry_result["industry"]
            stock.industry_code = industry_result["industry_code"]
            # 更新数据库中的行业信息
            db.commit()
            db.refresh(stock)
    
    if stock.industry and stock.industry != "未知":
        # 检查是否已有行业风险数据
        industry_risk = persistence_manager.get_industry_risk(stock.industry, scan_date)
        if not industry_risk:
            # 调用AI获取行业风险
            risk_data = ai_engine.get_industry_risk(stock.industry, scan_date.isoformat())
            if risk_data:
                persistence_manager.save_industry_risk({
                    "industry": stock.industry,
                    "analyze_date": scan_date,
                    "risk_analysis": risk_data["risk_analysis"]
                })
                industry_risk = persistence_manager.get_industry_risk(stock.industry, scan_date)
    
    return {
        "id": stock.id,
        "stock_code": stock.stock_code,
        "stock_name": stock.stock_name,
        "scan_date": stock.scan_date,
        "total_triggers": stock.total_triggers,
        "triggered_rules": stock.triggered_rules,
        "industry": stock.industry,
        "industry_code": stock.industry_code,
        "industry_risk": industry_risk.risk_analysis if industry_risk else None,
        "created_at": stock.created_at
    }


@app.get("/api/anomaly/export")
async def export_anomaly_stocks(target_date: date, db: Session = Depends(get_db)):
    """导出异动个股清单"""
    persistence_manager = PersistenceManager(db)
    stocks = persistence_manager.get_anomaly_stocks_by_date(target_date)
    
    # 创建CSV文件
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 写入表头
    writer.writerow(["股票代码", "股票名称", "扫描日期", "触发规则数", "所属行业", "触发规则列表"])
    
    # 写入数据
    for stock in stocks:
        rule_names = ", ".join([rule["rule_name"] for rule in stock.triggered_rules])
        writer.writerow([
            stock.stock_code,
            stock.stock_name,
            stock.scan_date.isoformat(),
            stock.total_triggers,
            stock.industry or "未知",
            rule_names
        ])
    
    output.seek(0)
    
    # 返回CSV文件
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=anomaly_stocks_{scan_date.isoformat()}.csv"
        }
    )


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
