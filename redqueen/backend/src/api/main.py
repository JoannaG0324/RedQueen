from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
from datetime import date, datetime, timedelta
import uuid
import csv
import io
from typing import List, Dict, Any

from src.utils.database import get_db, Base, engine

# 导入所有模型类，确保创建数据库表时包含所有表结构
from src.models.persistence_models import PersistenceManager, TaskStatus
from src.models.rule_models import RuleManager, TriggeredRule
from src.models.stock_models import StockDailyQfq, IndustryThs, IndustryThsStock, StockDailyQfqCalc

# 创建所有表（如果不存在）
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
    # 确定目标日期
    if target_date:
        target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        target_date_obj = date.today()
    
    # 检查是否为交易日
    data_reader = DataReader(db)
    if not data_reader.is_trading_day(target_date_obj):
        raise HTTPException(status_code=400, detail=f"{target_date_obj} 非交易日，无法执行扫描任务")
    
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
        processed_count = 0
        
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
                
                # 获取股票行业信息
                industry_info = data_reader.get_stock_industry(stock_code)
                
                # 构建异动个股数据
                stock_data = {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "scan_date": date.today(),
                    "target_date": target_date,
                    "total_triggers": result["total_triggers"],
                    "triggered_rules": triggered_rules_with_chinese,
                    "industry": industry_info["industry"] or "未知",
                    "industry_code": industry_info["industry_code"] or ""
                }
                anomaly_stocks.append(stock_data)
            
            # 更新处理进度
            processed_count += 1
            if processed_count % 100 == 0:
                persistence_manager.update_scan_task(task_id, {"processed_stocks": processed_count})
        
        # 计算日期范围用于暴露频率规则
        from datetime import timedelta
        three_day_start = target_date - timedelta(days=3)
        five_day_start = target_date - timedelta(days=5)
        
        # 获取历史异动数据
        historical_stocks = persistence_manager.get_anomaly_stocks_by_date_range(five_day_start, target_date)
        
        # 统计每个股票在不同时间范围内的异动次数
        stock_frequency = {}
        for stock in historical_stocks:
            if stock.stock_code not in stock_frequency:
                stock_frequency[stock.stock_code] = {'3_day': 0, '5_day': 0}
            
            # 计算5天内的次数
            stock_frequency[stock.stock_code]['5_day'] += 1
            
            # 计算3天内的次数
            if stock.target_date >= three_day_start:
                stock_frequency[stock.stock_code]['3_day'] += 1
        
        # 检查暴露频率规则并更新异动个股数据
        for stock_data in anomaly_stocks:
            stock_code = stock_data['stock_code']
            frequency = stock_frequency.get(stock_code, {'3_day': 0, '5_day': 0})
            
            # 检查是否满足暴露频率规则
            if frequency['3_day'] >= 2 or frequency['5_day'] >= 3:
                # 检查是否已存在该规则
                rule_exists = any(rule['rule_name'] == 'rule_exposure_frequency' for rule in stock_data['triggered_rules'])
                if not rule_exists:
                    # 添加暴露频率规则
                    stock_data['triggered_rules'].append({
                        'rule_name': 'rule_exposure_frequency',
                        'rule_chinese_name': '暴露频率异动',
                        'details': {
                            'three_day_count': frequency['3_day'],
                            'five_day_count': frequency['5_day']
                        }
                    })
                    stock_data['total_triggers'] += 1
        
        # 批量保存异动个股
        if anomaly_stocks:
            persistence_manager.save_batch_anomaly_stocks(anomaly_stocks)
        
        # 更新任务状态为完成
        persistence_manager.update_scan_task(
            task_id,
            {
                "status": TaskStatus.COMPLETED,
                "end_time": datetime.now(),
                "processed_stocks": processed_count
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
async def get_anomaly_stock(stock_code: str, target_date: date, get_risk: str = "false", db: Session = Depends(get_db)):
    # 将字符串转换为布尔值
    get_risk_bool = get_risk.lower() == "true"
    """获取异动个股详情"""
    persistence_manager = PersistenceManager(db)
    stock = persistence_manager.get_anomaly_stock_by_code_and_date(stock_code, target_date)
    
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    
    # 获取行业风险 - 只有当 get_risk 为 True 时才调用AI
    industry_risk = None
    if get_risk_bool:
        # 检查是否已有行业风险数据（使用股票代码作为标识）
        industry_risk = persistence_manager.get_industry_risk(stock_code, target_date)
        if not industry_risk:
            # 直接调用AI获取行业风险，AI会自动进行个股-行业映射
            risk_data = ai_engine.get_industry_risk(f"{stock_code} {stock.stock_name}", target_date.isoformat())
            if risk_data:
                persistence_manager.save_industry_risk({
                    "industry": stock_code,  # 使用股票代码作为industry字段
                    "analyze_date": target_date,
                    "risk_analysis": risk_data["risk_analysis"]
                })
                industry_risk = persistence_manager.get_industry_risk(stock_code, target_date)
    else:
        # 不获取行业风险，只检查是否已有数据
        industry_risk = persistence_manager.get_industry_risk(stock_code, target_date)
    
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
            "Content-Disposition": f"attachment; filename=anomaly_stocks_{target_date.isoformat()}.csv"
        }
    )


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/stock/latest-trading-day")
async def get_latest_trading_day(db: Session = Depends(get_db)):
    """获取最新的交易日"""
    # 查询 StockDailyQfq 表中最新的日期
    latest_date = db.query(func.max(StockDailyQfq.date)).scalar()
    return {"date": latest_date.isoformat() if latest_date else date.today().isoformat()}


@app.get("/api/stock/list", response_model=List[Dict[str, Any]])
async def get_stock_list(target_date: str, industry: str = "", stock_codes: str = "", db: Session = Depends(get_db)):
    """获取股票列表"""
    # 构建查询条件
    conditions = []
    conditions.append(f"sdqc.date = '{target_date}'")
    
    if industry:
        conditions.append(f"it.industry_name = '{industry}'")
    
    if stock_codes:
        # 解析股票代码列表
        stock_code_list = stock_codes.split(",")
        # 构建IN条件
        stock_code_str = ",".join([f"'{code}'" for code in stock_code_list])
        conditions.append(f"sdqc.stock_code IN ({stock_code_str})")
    
    condition_str = " AND ".join(conditions)
    
    # 构建 SQL 查询
    query = f"""
        SELECT sdqc.date, sdqc.stock_code, its.stock_name, 
               it.industry_name as industry,
               sd.close, sd.change_rate,
               sdqc.growth_streak_days, sdqc.growth_streak_pct
        FROM stock_daily_qfq_calc sdqc 
        LEFT JOIN stock_daily_qfq sd ON sd.stock_code = sdqc.stock_code AND sd.date = sdqc.date 
        LEFT JOIN industry_ths_stock its ON its.stock_code = sdqc.stock_code 
        LEFT JOIN industry_ths it ON it.industry_code = its.industry_code 
        WHERE {condition_str}
    """
    
    # 执行查询
    result = db.execute(text(query))
    rows = result.fetchall()
    
    # 构建返回数据
    stock_data_list = []
    for row in rows:
        stock_data_list.append({
            "date": row[0].isoformat() if row[0] else None,
            "stock_code": row[1],
            "stock_name": row[2],
            "industry": row[3],
            "close": row[4],
            "change_rate": row[5],
            "growth_streak_days": row[6],
            "growth_streak_pct": row[7]
        })
    
    return stock_data_list


@app.get("/api/stock/kline/{stock_code}", response_model=List[Dict[str, Any]])
async def get_stock_kline(stock_code: str, days: int = 20, end_date: str = None, db: Session = Depends(get_db)):
    """获取股票 K 线数据"""
    data_reader = DataReader(db)
    
    # 确定目标日期
    if end_date:
        # 如果提供了结束日期，使用该日期
        target_date = datetime.fromisoformat(end_date).date()
    else:
        # 否则使用最新的交易日
        latest_trading_day = db.query(func.max(StockDailyQfq.date)).scalar()
        if not latest_trading_day:
            return []
        target_date = latest_trading_day
    
    # 使用合理的默认值，避免数据校验失败
    # 当days超过365时，使用365作为数据校验的标准
    validate_days = min(days, 365)
    
    # 获取股票数据
    stock_data = data_reader.get_stock_data_by_date(stock_code, target_date, validate_days)
    
    if not stock_data:
        return []
    
    # 构建 K 线数据
    kline_data = []
    for i, date_str in enumerate(stock_data["dates"]):
        current_date = datetime.fromisoformat(date_str).date()
        
        # 获取技术指标数据
        tech_data = data_reader.db.query(StockDailyQfqCalc).filter(
            and_(
                StockDailyQfqCalc.stock_code == stock_code,
                StockDailyQfqCalc.date == current_date
            )
        ).first()
        
        ma5 = tech_data.ma5 if tech_data else None
        ma10 = tech_data.ma10 if tech_data else None
        ma20 = tech_data.ma20 if tech_data else None
        ma60 = tech_data.ma60 if tech_data else None
        ma120 = tech_data.ma120 if tech_data else None
        
        kline_data.append({
            "date": date_str,
            "open": stock_data["open"][i] if i < len(stock_data["open"]) else None,
            "close": stock_data["close"][i] if i < len(stock_data["close"]) else None,
            "high": stock_data["high"][i] if i < len(stock_data["high"]) else None,
            "low": stock_data["low"][i] if i < len(stock_data["low"]) else None,
            "volume": stock_data["volume"][i] if i < len(stock_data["volume"]) else None,
            "amount": stock_data["amount"][i] if i < len(stock_data["amount"]) else None,
            "change_rate": stock_data["change_rate"][i] if i < len(stock_data["change_rate"]) else None,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120
        })
    
    return kline_data


from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    prompt: str


@app.post("/api/ai/analyze", response_model=Dict[str, Any])
async def analyze_opportunity_stocks(request: AnalyzeRequest, db: Session = Depends(get_db)):
    """分析机会个股"""
    try:
        # 导入prompt模板
        from src.utils.prompts import OPPORTUNITY_ANALYSIS_PROMPT
        
        # 使用模板构建prompt
        prompt = OPPORTUNITY_ANALYSIS_PROMPT.format(user_input=request.prompt)
        
        # 调用AI引擎分析
        result = ai_engine.call_doubao_api(prompt)
        
        if not result:
            raise HTTPException(status_code=500, detail="AI分析失败")
        
        # 提取分析结果
        analysis = ""
        if "choices" in result and isinstance(result["choices"], list):
            for choice in result["choices"]:
                if "message" in choice and "content" in choice["message"]:
                    analysis = choice["message"]["content"]
                    break
        elif "output" in result and isinstance(result["output"], list):
            for item in result["output"]:
                if "content" in item:
                    if isinstance(item["content"], list):
                        for content_item in item["content"]:
                            if "text" in content_item:
                                analysis = content_item["text"]
                                break
                    elif isinstance(item["content"], str):
                        analysis = item["content"]
                    break
        
        if not analysis:
            raise HTTPException(status_code=500, detail="无法提取分析结果")
        
        return {
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.get("/api/industry/list", response_model=List[Dict[str, Any]])
async def get_industry_list(target_date: str, db: Session = Depends(get_db)):
    """获取行业列表数据"""
    try:
        # 解析日期
        target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # 检查是否为交易日
        data_reader = DataReader(db)
        if not data_reader.is_trading_day(target_date_obj):
            raise HTTPException(status_code=400, detail=f"{target_date} 非交易日，无法获取行业数据")
        
        # 获取行业数据
        industry_data = data_reader.get_industry_data(target_date_obj)
        
        return industry_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行业数据失败: {str(e)}")


@app.get("/api/industry/kline/{industry_code}", response_model=List[Dict[str, Any]])
async def get_industry_kline(industry_code: str, days: int = 20, end_date: str = None, db: Session = Depends(get_db)):
    """获取行业K线数据"""
    try:
        # 确定结束日期
        if end_date:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end_date_obj = date.today()
        
        # 检查是否为交易日
        data_reader = DataReader(db)
        if not data_reader.is_trading_day(end_date_obj):
            # 如果不是交易日，找到最近的交易日
            for i in range(1, 10):
                prev_date = end_date_obj - timedelta(days=i)
                if data_reader.is_trading_day(prev_date):
                    end_date_obj = prev_date
                    break
        
        # 获取行业K线数据
        kline_data = data_reader.get_industry_kline_data(industry_code, days, end_date_obj)
        
        return kline_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取行业K线数据失败: {str(e)}")
