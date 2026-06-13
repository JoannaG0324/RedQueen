from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Body
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
from src.models.stock_models import StockDailyQfq, StockDailyAnalysis, IndustryThs, IndustryThsStock, StockDailyQfqCalc, StockFavorite

# 创建所有表（如果不存在）
Base.metadata.create_all(bind=engine)
from src.data.data_reader import DataReader
from src.engine.rule_engine import RuleEngine
from src.engine.ai_engine import AIEngine

# 导入Skill系统
from src.skills import SkillRegistry, OpportunityAnalysisSkill

# 确保Skill被注册（显式初始化）
def initialize_skills():
    if not SkillRegistry.has_skill("opportunity_analysis"):
        from src.skills.opportunity_analysis import OpportunityAnalysisSkill
        SkillRegistry.register(OpportunityAnalysisSkill)
        print("Skill注册完成: opportunity_analysis")
    else:
        print("Skill已注册: opportunity_analysis")

# 初始化Skill
initialize_skills()

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
async def get_anomaly_stock(stock_code: str, target_date: date, db: Session = Depends(get_db)):
    """获取异动个股详情"""
    persistence_manager = PersistenceManager(db)
    stock = persistence_manager.get_anomaly_stock_by_code_and_date(stock_code, target_date)
    
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    
    return {
        "id": stock.id,
        "stock_code": stock.stock_code,
        "stock_name": stock.stock_name,
        "scan_date": stock.scan_date,
        "total_triggers": stock.total_triggers,
        "triggered_rules": stock.triggered_rules,
        "industry": stock.industry,
        "industry_code": stock.industry_code,
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
    # 查询 StockDailyAnalysis 表中最新的日期
    latest_date = db.query(func.max(StockDailyAnalysis.date)).scalar()
    return {"date": latest_date.isoformat() if latest_date else date.today().isoformat()}


@app.get("/api/stock/list", response_model=List[Dict[str, Any]])
async def get_stock_list(target_date: str = None, industry: str = "", stock_codes: str = "", db: Session = Depends(get_db)):
    """获取股票列表 - 若未指定 target_date，则默认使用数据库中最新的交易日"""
    # 未指定日期时，使用数据库中最新交易日
    if not target_date:
        latest_date = db.query(func.max(StockDailyQfqCalc.date)).scalar()
        if not latest_date:
            return []
        target_date = latest_date.isoformat()

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

    # 计算前一日日期
    target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    prev_date_obj = target_date_obj - timedelta(days=1)
    prev_date_str = prev_date_obj.isoformat()

    # 构建 SQL 查询 - 包含前一日成交量和计算指标
    query = f"""
        SELECT
            sdqc.date, sdqc.stock_code, COALESCE(sd.stock_name, its.stock_name) as stock_name,
            it.industry_name as industry,
            sd.close, sd.change_rate, sd.turnover,
            sdqc.growth_streak_days, sdqc.growth_streak_pct,
            sd.volume,
            COALESCE(sd_prev.volume, 0) as prev_volume,
            CASE
                WHEN sd.turnover IS NOT NULL AND sd.turnover > 0
                THEN sd.amount / (sd.turnover / 100) * 1.2
                ELSE NULL
            END as market_cap_r,
            CASE
                WHEN sd_prev.volume IS NOT NULL AND sd_prev.volume > 0
                THEN (sd.volume / sd_prev.volume - 1) * 100
                ELSE NULL
            END as volume_pct
        FROM stock_daily_qfq_calc sdqc
        LEFT JOIN stock_daily_analysis sd ON sd.stock_code = sdqc.stock_code AND sd.date = sdqc.date
        LEFT JOIN stock_daily_analysis sd_prev ON sd_prev.stock_code = sdqc.stock_code AND sd_prev.date = '{prev_date_str}'
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
            "turnover": row[6],
            "growth_streak_days": row[7],
            "growth_streak_pct": row[8],
            "volume": row[9],
            "market_cap_r": row[11],
            "volume_pct": row[12]
        })

    return stock_data_list


@app.get("/api/stock/kline/{stock_code}", response_model=List[Dict[str, Any]])
async def get_stock_kline(stock_code: str, days: int = 20, end_date: str = None, db: Session = Depends(get_db)):
    """获取股票 K 线数据"""
    data_reader = DataReader(db)

    # 预先计算"最新交易日"，用于两次查询的公共回退
    latest_trading_day = db.query(func.max(StockDailyAnalysis.date)).scalar()

    # 确定目标日期
    if end_date:
        # 如果提供了结束日期，使用该日期；若查询结果为空再回退到最新交易日
        target_date = datetime.fromisoformat(end_date).date()
    else:
        if not latest_trading_day:
            return []
        target_date = latest_trading_day

    # 使用合理的默认值，避免数据校验失败
    # 当days超过365时，使用365作为数据校验的标准
    validate_days = min(days, 365)

    # 获取股票数据
    stock_data = data_reader.get_stock_data_by_date(stock_code, target_date, validate_days)

    # 兜底：当 end_date 与实际数据不一致时，回退到最新交易日再查一次
    if (not stock_data) and end_date and latest_trading_day and target_date != latest_trading_day:
        stock_data = data_reader.get_stock_data_by_date(stock_code, latest_trading_day, validate_days)

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
    skill_name: str = "opportunity_analysis"


@app.post("/api/ai/analyze", response_model=Dict[str, Any])
async def analyze_opportunity_stocks(request: AnalyzeRequest):
    """分析机会个股 - 使用Skill架构（支持选择不同Skill）"""
    try:
        # 获取指定的Skill实例（默认使用opportunity_analysis）
        skill_name = request.skill_name
        if not SkillRegistry.has_skill(skill_name):
            raise HTTPException(status_code=404, detail=f"Skill不存在: {skill_name}")
        
        skill_class = SkillRegistry.get(skill_name)
        skill_instance = skill_class()
        
        # 执行Skill
        result = skill_instance.execute(user_prompt=request.prompt)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "analysis": result["analysis"],
            "stock_list": result.get("stock_list", []),
            "confidence": result.get("confidence", 0),
            "metadata": result.get("metadata", {})
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.get("/api/ai/skills", response_model=List[Dict[str, Any]])
async def list_skills():
    """获取所有已注册的Skill列表"""
    return SkillRegistry.list_skills()


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


@app.get("/api/heatmap/data", response_model=List[Dict[str, Any]])
async def get_heatmap_data(date1: str, date2: str, db: Session = Depends(get_db)):
    """获取行业个股热力图数据"""
    try:
        # 解析日期参数
        date1_obj = datetime.strptime(date1, "%Y-%m-%d").date()
        date2_obj = datetime.strptime(date2, "%Y-%m-%d").date()
        
        # 验证日期顺序
        if date1_obj >= date2_obj:
            raise HTTPException(status_code=400, detail="起始日期必须早于结束日期")
        
        # 构建SQL查询
        query = """
            SELECT 
                it.industry_code,
                it.industry_name,
                its.stock_code,
                COALESCE(its.stock_name, s.stock_name) as stock_name,
                # 计算自定义市值 Market(R) = amount / (turnover / 100) * 1.2
                CASE 
                    WHEN s2.turnover IS NOT NULL AND s2.turnover > 0 
                    THEN s2.amount / (s2.turnover / 100) * 1.2 
                    ELSE NULL 
                END as market_cap_r,
                # 计算个股区间涨跌幅
                CASE 
                    WHEN s1.close IS NOT NULL AND s1.close > 0 AND s2.close IS NOT NULL 
                    THEN (s2.close / s1.close) - 1 
                    ELSE NULL 
                END as change_pct,
                # 计算行业区间涨跌幅（基于行业指数）
                CASE 
                    WHEN i1.close IS NOT NULL AND i1.close > 0 AND i2.close IS NOT NULL 
                    THEN (i2.close / i1.close) - 1 
                    ELSE NULL 
                END as industry_change_pct
            FROM industry_ths it
            JOIN industry_ths_stock its ON it.industry_code = its.industry_code
            LEFT JOIN stock_daily_analysis s1 ON its.stock_code = s1.stock_code AND s1.date = :date1
            LEFT JOIN stock_daily_analysis s2 ON its.stock_code = s2.stock_code AND s2.date = :date2
            LEFT JOIN (
                SELECT stock_code, stock_name 
                FROM stock_daily_analysis 
                WHERE date = :date2 
                AND stock_name IS NOT NULL 
                AND stock_name != ''
            ) s ON its.stock_code = s.stock_code
            LEFT JOIN industry_ths_index i1 ON it.industry_code = i1.industry_code AND i1.date = :date1
            LEFT JOIN industry_ths_index i2 ON it.industry_code = i2.industry_code AND i2.date = :date2
            WHERE it.flag = 1
            # 过滤异常数据
            AND (s2.turnover IS NULL OR s2.turnover > 0)
            AND s1.close IS NOT NULL 
            AND s2.close IS NOT NULL
            ORDER BY it.industry_code, its.stock_code
        """
        
        # 执行查询
        result = db.execute(text(query), {"date1": date1_obj, "date2": date2_obj})
        rows = result.fetchall()
        
        # 构建返回数据
        heatmap_data = []
        for row in rows:
            heatmap_data.append({
                "industry_code": row[0],
                "industry_name": row[1],
                "stock_code": row[2],
                "stock_name": row[3],
                "market_cap_r": float(row[4]) if row[4] else None,
                "change_pct": float(row[5]) if row[5] else None,
                "industry_change_pct": float(row[6]) if row[6] else None
            })
        
        return heatmap_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取热力图数据失败: {str(e)}")


# 全局变量，用于跟踪正在执行的任务
running_tasks = {}

@app.post("/api/data/execute", response_model=Dict[str, Any])
async def execute_data_task(task_id: str, page: str = "1", target_date: str = None, db: Session = Depends(get_db)):
    """执行数据获取任务"""
    try:
        # 记录任务开始
        running_tasks[task_id] = True
        
        # 执行update_stock_daily_backup任务
        if task_id == "update_stock_daily_backup":
            # 导入update_stock_daily_backup模块
            from src.data.update_stock_daily_backup import update_stock_daily, process_stock_daily, fetch_stock_data_selenium_plus
            
            # 解析页码参数
            start_page = 1
            end_page = None
            
            if page == "251-":
                # 选择"251-"时，从第251页到实际最后一页
                start_page = 251
                end_page = None
            elif "-" in page:
                # 自定义范围格式："start-end"
                parts = page.split("-")
                start_page = int(parts[0]) if parts[0].isdigit() else 1
                if len(parts) > 1 and parts[1].isdigit():
                    end_page = int(parts[1])
            else:
                # 单页码格式，前端选择的是区间起始页
                # "1" 表示 1-50, "51" 表示 51-100, "101" 表示 101-150, 
                # "151" 表示 151-200, "201" 表示 201-250, "251" 表示 251-
                if page.isdigit():
                    page_num = int(page)
                    start_page = page_num
                    # 根据起始页计算结束页（每50页一个区间）
                    if page_num == 1:
                        end_page = 50
                    elif page_num == 51:
                        end_page = 100
                    elif page_num == 101:
                        end_page = 150
                    elif page_num == 151:
                        end_page = 200
                    elif page_num == 201:
                        end_page = 250
                    elif page_num == 251:
                        end_page = None  # 到实际最后一页
                    else:
                        start_page = page_num
            
            # 执行任务
            print(f"开始执行update_stock_daily_backup任务，从第 {start_page} 页开始" + (f"，到第 {end_page} 页结束" if end_page else ""))
            result = update_stock_daily(start_page=start_page, end_page=end_page)
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed" if result else "failed",
                "message": f"任务 {task_id} 执行完成，从第 {start_page} 页开始运行" + (f"，到第 {end_page} 页结束" if end_page else ""),
                "execution_time": datetime.now().isoformat(),
                "page": page
            }
        elif task_id == "update_industry_flow_data":
            # 导入update模块
            from src.data.update import update_industry_flow_data
            
            # 执行任务
            print("开始执行update_industry_flow_data任务")
            result = update_industry_flow_data()
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed" if result else "failed",
                "message": result if isinstance(result, str) else f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "update_stock_flow":
            # 导入update模块
            from src.data.update import update_stock_flow
            
            # 执行任务
            print("开始执行update_stock_flow任务")
            result = update_stock_flow()
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed" if result else "failed",
                "message": result if isinstance(result, str) else f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "update_stock_ztb_data":
            # 导入update模块
            from src.data.update import update_stock_ztb_data
            
            # 执行任务
            print("开始执行update_stock_ztb_data任务")
            result = update_stock_ztb_data()
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed" if result else "failed",
                "message": result if isinstance(result, str) else f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "update_stock_spot_data":
            # 导入update模块
            from src.data.update import update_stock_spot_data
            
            # 执行任务
            print("开始执行update_stock_spot_data任务")
            result = update_stock_spot_data()
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed" if result else "failed",
                "message": result if isinstance(result, str) else f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "update_industry_ths_index_daily":
            # 导入update_industry_ths_daily模块
            from src.data.update_industry_ths_daily import update_industry_ths_index_daily
            
            # 执行任务
            print("开始执行update_industry_ths_index_daily任务")
            update_industry_ths_index_daily()
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "industry_flow_calc":
            # 导入calc_cash_flow模块
            from src.data.calc_cash_flow import industry_flow_calc
            
            # 执行任务
            print("开始执行industry_flow_calc任务")
            industry_flow_calc(engine)
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": "行业板块资金流计算完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "daily_process_industry_indicators":
            # 导入calc_price模块
            from src.data.calc_price import daily_process_industry_indicators
            
            # 执行任务
            print("开始执行daily_process_industry_indicators任务")
            daily_process_industry_indicators(max_workers=10)
            
            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": "行业基础量价指标计算完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "daily_process_stock_indicators":
            # 导入calc_price模块
            from src.data.calc_price import daily_process_stock_indicators

            # 执行任务
            print("开始执行daily_process_stock_indicators任务")
            daily_process_stock_indicators(max_workers=10)

            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": "个股量价指标计算完成",
                "execution_time": datetime.now().isoformat()
            }
        elif task_id == "stock_daily_calc_update_incremental":
            # 导入calc_hl_mid模块：个股补充指标（滚动高低点-增量）
            from src.data.calc_hl_mid import run_incremental

            # 执行任务
            print("开始执行stock_daily_calc_update_incremental（个股补充指标-增量）任务")
            stats = run_incremental(batch_size=200)

            hit = stats.get("hit", {}) or {}
            inc = stats.get("incremental", {}) or {}

            message = (
                f"个股补充指标（滚动高低点 20/60/90/120D）计算完成，"
                f"总写入 {stats.get('rows_written', 0)} 行，"
                f"总覆盖股票 {stats.get('stocks', 0)} 只，"
                f"区间 {stats.get('start_date', '')} ~ {stats.get('end_date', '')}"
            )
            detail = (
                f"【跳空命中-全量重算】"
                f" {hit.get('stocks', 0)} 只股票，写入 {hit.get('rows_written', 0)} 行；"
                f"【未命中-增量更新】"
                f" {inc.get('stocks', 0)} 只股票，写入 {inc.get('rows_written', 0)} 行"
            )

            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": message,
                "detail": detail,
                "execution_time": datetime.now().isoformat(),
                "stats": stats,
            }
        elif task_id == "industry_ths_index_calc_update_incremental":
            # 导入calc_hl_mid_industry模块：行业补充指标（滚动高低点-增量）
            from src.data.calc_hl_mid_industry import run_incremental

            # 执行任务
            print("开始执行industry_ths_index_calc_update_incremental（行业补充指标-增量）任务")
            stats = run_incremental(batch_size=50)

            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": (
                    "行业补充指标（滚动高低点 20/60/90/120D）计算完成，"
                    f"写入 {stats.get('rows_written', 0)} 行，"
                    f"覆盖行业 {stats.get('industries', 0)} 个，"
                    f"区间 {stats.get('start_date', '')} ~ {stats.get('end_date', '')}"
                ),
                "execution_time": datetime.now().isoformat(),
                "stats": stats,
            }
        elif task_id == "init_qfq_mark_scan_incremental":
            # 导入init_qfq_mark_scan模块：前复权扫描（增量版）
            from src.data.init_qfq_mark_scan import run_incremental

            # 执行任务
            print("开始执行init_qfq_mark_scan_incremental（前复权增量扫描）任务")
            stats = run_incremental(batch_size=500)

            message = (
                f"stock_qfq_mark 增量扫描完成，"
                f"扫描 {stats.get('total_stocks', 0)} 只股票，"
                f"本轮标记 {stats.get('marked_stocks', 0)} 只，"
                f"最新交易日 {stats.get('latest_trade_day', '')}"
            )

            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": message,
                "execution_time": datetime.now().isoformat(),
                "stats": stats,
            }
        elif task_id == "fetch_kline_to_analysis":
            # 导入fetch_kline_to_analysis模块：前复权K线覆盖写入
            from src.data.fetch_kline_to_analysis import run_loop

            # 执行任务
            print("开始执行fetch_kline_to_analysis（前复权K线覆盖更新）任务")
            stats = run_loop(market=None, lmt=500)

            message = (
                f"前复权 K 线覆盖更新完成，"
                f"共 {stats.get('total', 0)} 只股票，"
                f"成功 {stats.get('succeeded', 0)} 只，"
                f"失败 {stats.get('failed', 0)} 只，"
                f"总耗时 {round(stats.get('elapsed_sec', 0), 1)}s"
            )

            # 构建任务结果
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": message,
                "execution_time": datetime.now().isoformat(),
                "stats": stats,
            }
        elif task_id == "duplicate_check":
            # 数据重复扫描：对 stock_daily_qfq_new 查询 (stock_code, date) 重复项
            from sqlalchemy import text as sql_text

            # 优先使用传入的 target_date；未传入则用表内最大日期
            check_date = target_date
            if check_date is None or str(check_date).strip() == "":
                try:
                    with db.begin():
                        row = db.execute(
                            sql_text("SELECT MAX(date) FROM stock_daily_qfq_new")
                        ).scalar()
                    if row is not None:
                        check_date = str(row)
                    else:
                        check_date = datetime.now().strftime("%Y-%m-%d")
                except Exception:
                    check_date = datetime.now().strftime("%Y-%m-%d")

            print(f"开始执行 duplicate_check（数据重复扫描）任务，日期 = {check_date}")

            sql = sql_text("""
                SELECT
                    CASE WHEN id % 20 = 0 THEN 0 ELSE id % 20 END AS FLAG,
                    CEIL(id / 20) AS PAGE,
                    CONCAT(
                        'id>', id - (CASE WHEN id % 20 = 0 THEN 20 ELSE id % 20 END),
                        ' and id<=', 20 * FLOOR((id + 19) / 20)
                    ) AS `ID_conditions`,
                    temp.*
                FROM (
                    SELECT
                        *,
                        COUNT(*) OVER (PARTITION BY stock_code, date) AS repeat_cnt
                    FROM stock_daily_qfq_new
                    WHERE date = :check_date
                ) temp
                WHERE repeat_cnt > 1
                ORDER BY FLAG
            """)

            try:
                with db.begin():
                    rows = db.execute(sql, {"check_date": check_date}).mappings().all()
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"数据重复扫描执行失败: {str(e)}"
                )

            rows_list = [dict(r) for r in rows]
            total_dupes = len(rows_list)

            if total_dupes == 0:
                message = f"日期 {check_date}：未检测到重复数据"
                status_val = "completed"
            else:
                # 统计涉及多少组 (stock_code, date) 组合
                unique_keys = set()
                for r in rows_list:
                    key = (str(r.get("stock_code", "")), str(r.get("date", "")))
                    unique_keys.add(key)
                sample_preview = rows_list[:5]  # 附带前 5 行用于排查
                message = (
                    f"日期 {check_date}：发现 {total_dupes} 条重复记录，"
                    f"涉及 {len(unique_keys)} 组 (stock_code, date) 组合【存在异常数据】"
                )
                status_val = "completed"

                # 构建任务结果（附带详细数据用于前端展示）
                result = {
                    "task_id": task_id,
                    "status": status_val,
                    "message": message,
                    "check_date": check_date,
                    "total_dupes": total_dupes,
                    "affected_groups": len(unique_keys),
                    "sample": sample_preview,
                    "execution_time": datetime.now().isoformat(),
                }
                # 提前返回，跳过下方统一的 result 构建
                if task_id in running_tasks:
                    del running_tasks[task_id]
                return result

            # 无重复数据的路径（复用原有 result 模式）
            result = {
                "task_id": task_id,
                "status": status_val,
                "message": message,
                "check_date": check_date,
                "total_dupes": 0,
                "affected_groups": 0,
                "execution_time": datetime.now().isoformat(),
            }
        else:
            # 模拟执行其他任务
            import time
            time.sleep(2)  # 模拟任务执行时间
            
            result = {
                "task_id": task_id,
                "status": "completed",
                "message": f"任务 {task_id} 执行完成",
                "execution_time": datetime.now().isoformat()
            }
        
        # 任务完成，从运行列表中移除
        if task_id in running_tasks:
            del running_tasks[task_id]
        
        return result
    except Exception as e:
        # 任务失败，从运行列表中移除
        if task_id in running_tasks:
            del running_tasks[task_id]
        print(f"执行任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行任务失败: {str(e)}")


@app.post("/api/data/stop", response_model=Dict[str, Any])
async def stop_tasks():
    """终止所有正在执行的任务"""
    try:
        # 清空运行中的任务
        task_ids = list(running_tasks.keys())
        running_tasks.clear()
        
        # 构建响应
        result = {
            "status": "completed",
            "message": f"成功终止 {len(task_ids)} 个任务",
            "task_ids": task_ids,
            "execution_time": datetime.now().isoformat()
        }
        
        return result
    except Exception as e:
        print(f"终止任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"终止任务失败: {str(e)}")


# ========== 股票收藏接口 ==========


@app.get("/api/stock/favorites", response_model=List[Dict[str, Any]])
async def get_favorite_list(db: Session = Depends(get_db)):
    """获取所有收藏的股票代码列表（状态为 1 即"已收藏"）"""
    try:
        rows = db.query(StockFavorite).filter(StockFavorite.status == 1).all()
        return [
            {
                "stock_code": r.stock_code,
                "price_date": r.price_date.isoformat() if r.price_date else None,
                "status": r.status,
                "updated_time": r.updated_time.isoformat() if r.updated_time else None,
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询收藏列表失败: {str(e)}")


@app.get("/api/stock/favorite/{stock_code}", response_model=Dict[str, Any])
async def get_favorite_one(stock_code: str, db: Session = Depends(get_db)):
    """查询某只股票的收藏状态"""
    try:
        row = db.query(StockFavorite).filter(StockFavorite.stock_code == stock_code).first()
        if not row:
            return {"stock_code": stock_code, "status": 0, "price_date": None, "updated_time": None}
        return {
            "stock_code": row.stock_code,
            "price_date": row.price_date.isoformat() if row.price_date else None,
            "status": row.status,
            "updated_time": row.updated_time.isoformat() if row.updated_time else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询收藏状态失败: {str(e)}")


@app.post("/api/stock/favorite/{stock_code}", response_model=Dict[str, Any])
async def upsert_favorite(
    stock_code: str,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """收藏/取消收藏某只股票

    首次收藏时插入新记录；对同一只股票的后续操作按主键更新：
    - status=1 收藏时更新 price_date 与 updated_time
    - status=0 取消收藏时仅更新 status 和 updated_time，不覆盖 price_date
    """
    from datetime import datetime as _dt
    try:
        price_date_raw = payload.get("price_date")
        status = payload.get("status")
        if status is None or status not in (0, 1):
            raise HTTPException(status_code=400, detail="参数 status 必须为 0 或 1")
        price_date = None
        if price_date_raw:
            try:
                price_date = _dt.strptime(str(price_date_raw), "%Y-%m-%d").date()
            except Exception:
                raise HTTPException(status_code=400, detail="price_date 格式错误，应为 YYYY-MM-DD")

        now = _dt.now()
        row = db.query(StockFavorite).filter(StockFavorite.stock_code == stock_code).first()
        if row is None:
            if not price_date:
                price_date = now.date()
            new_row = StockFavorite(
                stock_code=stock_code,
                price_date=price_date,
                status=status,
                updated_time=now,
            )
            db.add(new_row)
            db.commit()
            db.refresh(new_row)
            return {
                "stock_code": new_row.stock_code,
                "price_date": new_row.price_date.isoformat() if new_row.price_date else None,
                "status": new_row.status,
                "updated_time": new_row.updated_time.isoformat() if new_row.updated_time else None,
                "action": "insert",
            }
        else:
            row.status = status
            row.updated_time = now
            if status == 1 and price_date is not None:
                row.price_date = price_date
            db.commit()
            db.refresh(row)
            return {
                "stock_code": row.stock_code,
                "price_date": row.price_date.isoformat() if row.price_date else None,
                "status": row.status,
                "updated_time": row.updated_time.isoformat() if row.updated_time else None,
                "action": "update",
            }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新收藏失败: {str(e)}")


@app.delete("/api/stock/favorite/{stock_code}", response_model=Dict[str, Any])
async def delete_favorite(stock_code: str, db: Session = Depends(get_db)):
    """删除某只股票的收藏记录"""
    try:
        row = db.query(StockFavorite).filter(StockFavorite.stock_code == stock_code).first()
        if not row:
            return {"status": "success", "message": "记录不存在", "stock_code": stock_code}
        db.delete(row)
        db.commit()
        return {"status": "success", "message": "已删除", "stock_code": stock_code}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除收藏失败: {str(e)}")
