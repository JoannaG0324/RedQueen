import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, text
import numpy as np
import pandas as pd
from src.utils.config import settings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 数据库连接配置
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

# 数据源与目标表配置
SOURCE_TABLE = "stock_daily_analysis"          # 行情数据源（前复权日线）
TARGET_TABLE = "stock_daily_qfq_calc"              # 指标计算结果表
MARK_TABLE = "stock_qfq_mark"                    # 标记表，用于跟踪全量/增量

# 创建数据库连接
engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

# ==================== 计算参数 ====================
# 注意：以下函数统一使用 "date 升序" 进行计算，再把结果按 "date 降序" 返回。
# 数据量不足时对应指标为 NaN，上游填充 None（由 DataFrame to_dict('records') 统一处理。
MA_PERIODS = [3, 5, 10, 20, 30, 60, 90, 120, 200]
ATR_PERIODS = [3, 5, 10, 14]

# 用于增量模式：仅在需要最近多少天的数据来计算指标（大于最大窗宽）
INCREMENTAL_WINDOW = 250

# 用于全量重算：一次性拉取多少天数据（覆盖常用窗宽，防止超长）
FULL_RECALC_LIMIT = 4000


# ==================== 通用计算函数 ====================

def _to_asc(df):
    """复制一份按 date 升序排序的 DataFrame，便于窗口计算。"""
    return df.sort_values("date", ascending=True).reset_index(drop=True)


def _fill_none_list(arr):
    """把 numpy / pandas 数值数组转成 Python list，NaN 替换为 None。"""
    out = []
    for v in arr:
        if pd.isna(v):
            out.append(None)
        else:
            out.append(float(v))
    return out


def calculate_moving_averages(df, periods=MA_PERIODS):
    """向量化移动平均线计算。对每个 period 使用 cumsum 做 O(n) 窗口均值。"""
    if df is None or len(df) == 0:
        return {f"ma{p}": [] for p in periods}

    asc = _to_asc(df)
    close = asc["close"].astype(float).values
    n = len(close)
    out = {}
    for p in periods:
        if p <= 0 or n < p:
            ma = np.full(n, np.nan)
        else:
            csum = np.r_[0.0, np.cumsum(close)]
            ma = (csum[p:] - csum[:-p]) / p
            ma = np.r_[np.full(p - 1, np.nan), ma]
        out[f"ma{p}"] = _fill_none_list(ma[::-1])
    return out


def calculate_atr(df, periods=ATR_PERIODS):
    """向量化 ATR 计算。TR = max(high-low, |high-prev_close|, |low-prev_close|)。"""
    if df is None or len(df) == 0:
        return {f"atr{p}": [] for p in periods}

    asc = _to_asc(df)
    high = asc["high"].astype(float).values
    low = asc["low"].astype(float).values
    close = asc["close"].astype(float).values
    n = len(close)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    tr = np.maximum(np.maximum(tr1, tr2), tr3)

    out = {}
    for p in periods:
        if p <= 0 or n < p:
            atr = np.full(n, np.nan)
        else:
            csum = np.r_[0.0, np.cumsum(tr)]
            atr = (csum[p:] - csum[:-p]) / p
            atr = np.r_[np.full(p - 1, np.nan), atr]
        out[f"atr{p}"] = _fill_none_list(atr[::-1])
    return out


def calculate_growth_streak(df):
    """连涨天数/连涨涨幅。从最新日期开始往历史回溯，遇下跌即停止。"""
    if df is None or len(df) == 0:
        return {"growth_streak_days": [], "growth_streak_pct": []}

    asc = _to_asc(df)
    close = asc["close"].astype(float).values
    n = len(close)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(prev_close != 0,
                       (close - prev_close) / prev_close * 100.0, 0.0)

    close_desc = close[::-1]
    pct_desc = pct[::-1]

    streak_days = np.zeros(n, dtype=float)
    streak_pct = np.zeros(n, dtype=float)

    # pct_desc[j] 语义："第 j 近的交易日"相对"其前一日"的涨跌幅
    # 连涨 = 从当前日 j=i 开始向历史方向（j 增大）遍历，直到遇到 pct_desc[j] <= 0 为止
    # 连涨天数 = N，基准价 = close_desc[i + N]（连涨序列起点之前那一天的收盘价）
    for i in range(n):
        if pd.isna(close_desc[i]):
            continue

        N = 0
        for j in range(i, n):
            pj = pct_desc[j]
            if pd.isna(pj) or pj < 0:
                break
            if pj > 0:
                N += 1
            # pj == 0 视为平盘，不计入连涨天数，也不中断（继续向前看）

        streak_days[i] = float(N)
        if N > 0 and i + N < n:
            base_price = close_desc[i + N]
            if base_price and base_price != 0:
                streak_pct[i] = (close_desc[i] / base_price - 1.0) * 100.0
            else:
                streak_pct[i] = 0.0
        else:
            streak_pct[i] = 0.0

    return {
        "growth_streak_days": _fill_none_list(streak_days),
        "growth_streak_pct": _fill_none_list(streak_pct),
    }


# ==================== 【个股数据】处理个股指标并写入数据库 ====================

def _calc_rows_for(df_stock, stock_code, dates_filter=None):
    """通用：在按 date 降序的 df_stock 上计算全部指标行。

    若 dates_filter 不为空，则仅保留日期在该列表中的行（通过 str(date) 匹配）。
    """
    n = len(df_stock)
    if n == 0:
        return []

    if n < 3:
        rows = []
        for i in range(n):
            date_i = df_stock.iloc[i]["date"]
            if dates_filter is not None and str(date_i) not in set(dates_filter):
                continue
            rows.append({
                "stock_code": stock_code,
                "date": date_i,
                "ma3": None, "ma5": None, "ma10": None,
                "ma20": None, "ma30": None, "ma60": None,
                "ma90": None, "ma120": None, "ma200": None,
                "atr3": None, "atr5": None, "atr10": None, "atr14": None,
                "growth_streak_days": None, "growth_streak_pct": None,
            })
        return rows

    ma_results = calculate_moving_averages(df_stock)
    atr_results = calculate_atr(df_stock)
    growth_results = calculate_growth_streak(df_stock)

    rows = []
    for i in range(n):
        date_i = df_stock.iloc[i]["date"]
        if dates_filter is not None and str(date_i) not in set(dates_filter):
            continue

        row = {"stock_code": stock_code, "date": date_i}
        for ma_col, ma_values in ma_results.items():
            row[ma_col] = ma_values[i] if i < len(ma_values) else None
        for atr_col, atr_values in atr_results.items():
            row[atr_col] = atr_values[i] if i < len(atr_values) else None
        row["growth_streak_days"] = (
            growth_results["growth_streak_days"][i]
            if i < len(growth_results["growth_streak_days"])
            else None
        )
        row["growth_streak_pct"] = (
            growth_results["growth_streak_pct"][i]
            if i < len(growth_results["growth_streak_pct"])
            else None
        )
        rows.append(row)
    return rows


def _bulk_insert_rows(rows, batch_size=1000):
    """按批插入，避免单次 SQL 参数过多。"""
    if not rows:
        return
    placeholders = (
        ":stock_code, :date, "
        ":ma3, :ma5, :ma10, :ma20, :ma30, :ma60, :ma90, :ma120, :ma200, "
        ":atr3, :atr5, :atr10, :atr14, "
        ":growth_streak_days, :growth_streak_pct"
    )
    cols = (
        "stock_code, date, "
        "ma3, ma5, ma10, ma20, ma30, ma60, ma90, ma120, ma200, "
        "atr3, atr5, atr10, atr14, "
        "growth_streak_days, growth_streak_pct"
    )
    ins_sql = text(
        f"INSERT INTO {TARGET_TABLE} ({cols}) VALUES ({placeholders})"
    )
    with engine.begin() as conn:
        for start in range(0, len(rows), batch_size):
            conn.execute(ins_sql, rows[start:start + batch_size])


def process_stock_indicators_recalc(stock_code):
    """对某只股票进行『全量重算』（stock_qfq_mark 中存在即标记为跳空命中）。

    步骤：
    1. 删除 TARGET_TABLE 中该股全部历史记录；
    2. 从 SOURCE_TABLE 读取最多 FULL_RECALC_LIMIT 条日线；
    3. 向量化计算全部交易日的指标；
    4. 批量插回 TARGET_TABLE。
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f"DELETE FROM {TARGET_TABLE} WHERE stock_code = :code"
            ), {"code": stock_code})

        query = text(f"""
            SELECT stock_code, date, open, close, high, low, volume, amount
            FROM {SOURCE_TABLE}
            WHERE stock_code = :code
            ORDER BY date DESC
            LIMIT :lim
        """)
        df_stock = pd.read_sql(query, engine,
                                params={"code": stock_code, "lim": FULL_RECALC_LIMIT})

        if df_stock.empty:
            print(f"  [重算] {stock_code} 在 {SOURCE_TABLE} 无数据，跳过")
            return False

        rows = _calc_rows_for(df_stock, stock_code, dates_filter=None)
        _bulk_insert_rows(rows)

        print(f"  [重算] {stock_code} 完成，写入 {len(rows)} 行")
        return True

    except Exception as exc:
        print(f"  [重算] {stock_code} 失败: {exc}")
        return False


def process_daily_stock_indicators(stock_code, target_date):
    """对某只股票进行『增量更新』，只计算 target_date 这一天的指标。

    只删除 TARGET_TABLE 中该股该日期的旧数据，并按最近 INCREMENTAL_WINDOW 天
    的行情计算指标，最后仅插入 target_date 一行。
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f"DELETE FROM {TARGET_TABLE} "
                f"WHERE stock_code = :code AND date = :d"
            ), {"code": stock_code, "d": target_date})

        query = text(f"""
            SELECT stock_code, date, open, close, high, low, volume, amount
            FROM {SOURCE_TABLE}
            WHERE stock_code = :code AND date <= :d
            ORDER BY date DESC
            LIMIT :lim
        """)
        df_stock = pd.read_sql(
            query, engine,
            params={"code": stock_code, "d": target_date,
                    "lim": INCREMENTAL_WINDOW},
        )

        if df_stock.empty:
            print(f"  [增量] {stock_code} 在 {SOURCE_TABLE} 无数据")
            return False

        rows = _calc_rows_for(df_stock, stock_code,
                               dates_filter=[str(target_date)])
        if not rows:
            return False

        _bulk_insert_rows(rows)
        return True

    except Exception as exc:
        print(f"  [增量] {stock_code} 失败: {exc}")
        return False


def daily_process_stock_indicators(max_workers=10):
    """每日处理函数：按 MARK_TABLE(stock_qfq_mark) 分流为全量重算与增量更新。

    - 全量重算：MARK_TABLE 中存在的股票（本轮被标记为跳空/除权）；
    - 其它股票：对 SOURCE_TABLE 的最新日期做每日增量更新；
    - 数据源全部使用 SOURCE_TABLE（= stock_daily_analysis）。
    """
    try:
        print(f"==== 每日指标计算处理 {TARGET_TABLE} ====")
        print(f"数据源: {SOURCE_TABLE}，标记表: {MARK_TABLE}")

        latest_df = pd.read_sql(
            text(f"SELECT MAX(date) as latest_date FROM {SOURCE_TABLE}"),
            engine,
        )
        latest_date = latest_df.iloc[0]["latest_date"]
        if latest_date is None or pd.isna(latest_date):
            print(f"未在 {SOURCE_TABLE} 中找到有效日期，请先更新；返回 None")
            return None

        print(f"最新数据日期: {latest_date}")

        codes_query = text(f"""
            SELECT DISTINCT stock_code FROM {SOURCE_TABLE} WHERE date = :d
        """)
        codes_df = pd.read_sql(codes_query, engine, params={"d": latest_date})
        all_codes = set(codes_df["stock_code"].tolist())

        try:
            mark_df = pd.read_sql(text(f"""
                SELECT DISTINCT stock_code FROM {MARK_TABLE}
            """), engine)
        except Exception:
            # 表未创建或临时不可用：回退为"全部走增量"
            mark_df = pd.DataFrame(columns=["stock_code"])

        # 跳空命中：只要在 stock_qfq_mark 中存在，即本轮需全量重算
        if mark_df.empty:
            recalc_codes = set()
        else:
            recalc_codes = set(mark_df["stock_code"].astype(str).tolist())

        # 仅对"在 SOURCE_TABLE 最新交易日中存在数据"的股票处理（避免标记一些已退市但还残留的代码）
        recalc_codes &= all_codes
        incremental_codes = list(all_codes - recalc_codes)
        recalc_codes = list(recalc_codes)

        print(f"全量重算 {len(recalc_codes)} 只，增量更新 {len(incremental_codes)} 只")

        start_time = time.time()
        stats = {"recalc_ok": 0, "recalc_fail": 0,
                 "incr_ok": 0, "incr_fail": 0}

        if recalc_codes:
            print(f"开始全量重算 {len(recalc_codes)} 只股票...")
            recalc_workers = max(2, max_workers // 2)
            with ThreadPoolExecutor(max_workers=recalc_workers) as ex:
                future_map = {
                    ex.submit(process_stock_indicators_recalc, c): c
                    for c in recalc_codes
                }
                processed = 0
                total = len(recalc_codes)
                for fut in as_completed(future_map):
                    code = future_map[fut]
                    processed += 1
                    try:
                        ok = fut.result()
                        if ok:
                            stats["recalc_ok"] += 1
                        else:
                            stats["recalc_fail"] += 1
                    except Exception as exc:
                        print(f"  {code} 重算异常: {exc}")
                        stats["recalc_fail"] += 1
                    if processed % 50 == 0 or processed == total:
                        print(f"  重算进度 {processed}/{total}")

        if incremental_codes:
            print(f"开始增量更新 {len(incremental_codes)} 只股票...")
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {
                    ex.submit(process_daily_stock_indicators, c, latest_date): c
                    for c in incremental_codes
                }
                processed = 0
                total = len(incremental_codes)
                for fut in as_completed(future_map):
                    code = future_map[fut]
                    processed += 1
                    try:
                        ok = fut.result()
                        if ok:
                            stats["incr_ok"] += 1
                        else:
                            stats["incr_fail"] += 1
                    except Exception as exc:
                        print(f"  {code} 增量异常: {exc}")
                        stats["incr_fail"] += 1
                    if processed % 500 == 0 or processed == total:
                        print(f"  增量进度 {processed}/{total}")

        total_time = time.time() - start_time
        print(f"\n每日处理完成！日期: {latest_date}")
        print("  全量重算:", stats["recalc_ok"], "成功，", stats["recalc_fail"], "失败")
        print("  增量更新:", stats["incr_ok"], "成功，", stats["incr_fail"], "失败")
        print(f"  总耗时: {total_time:.2f} 秒")

        return stats

    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise

# ==================== 【行业数据】初始化 处理行业数据并写入数据库 by industry_ths_index ====================

def process_industry_indicators(stock_code):
    """
    计算单个股票的指标并写入数据库（一体化函数，包含更新功能）
    
    Args:
        stock_code: 股票代码
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该股票的旧数据（更新模式）!update
        delete_sql = f"DELETE FROM industry_ths_index_calc WHERE industry_code = '{stock_code}'" # by industry_ths_index !update
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询单个股票的数据
        query = f"""
        SELECT industry_code, date, open, close, high, low, volume, amount
        FROM industry_ths_index
        WHERE industry_code = '{stock_code}'
        ORDER BY date DESC
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {stock_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"股票 {stock_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                row_data = {
                    'industry_code': stock_code, #!update
                    'date': df_stock.iloc[i]['date'],
                    'ma3': None,
                    'ma5': None,
                    'ma10': None,
                    'ma20': None,
                    'ma30': None,
                    'ma60': None,
                    'ma90': None,
                    'ma120': None,
                    'ma200': None,
                    'atr3': None,
                    'atr5': None,
                    'atr10': None,
                    'atr14': None
                }
                calc_data.append(row_data)
            
            # 转换为DataFrame
            df_calc = pd.DataFrame(calc_data)
            
            # 存储到数据库（使用append模式）
            df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', #!update
                          index=False, method='multi')
            
            print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
            return True
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)
        
        # 准备插入数据
        calc_data = []
        for i in range(len(df_stock)):
            row_data = {
                'industry_code': stock_code, #!update
                'date': df_stock.iloc[i]['date'],
            }
            
            # 添加MA数据
            for ma_col, ma_values in ma_results.items():
                row_data[ma_col] = ma_values[i]
            
            # 添加ATR数据
            for atr_col, atr_values in atr_results.items():
                row_data[atr_col] = atr_values[i]
            
            calc_data.append(row_data)
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理股票 {stock_code} 时出现错误: {str(e)}")
        return False
    
    print("计算结果表创建完成")

def calculate_industry_indicators_multithreaded(stock_codes=None, max_workers=10):
    """
    使用多线程计算股票指标（统一函数，支持计算全部股票或指定股票）
    
    Args:
        stock_codes: 股票代码列表，如果为None则计算所有股票
        max_workers: 最大线程数，默认为4
        
    Returns:
        dict: 包含成功和失败统计的字典
    """
        
    try:
        # 创建计算结果表
        # create_calc_table()
        
        if stock_codes is None:
            print(f"stock_codes 为空，不进行计算")
        elif isinstance(stock_codes, str):
            stock_codes = [stock_codes]
            print(f"开始计算指定 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        else:
            print(f"开始批量计算 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_stock = {executor.submit(process_industry_indicators, stock_code): stock_code 
                             for stock_code in stock_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(stock_codes)
            processed = 0
            
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'股票 {stock_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 股票 {stock_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"多线程计算完成！")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票") 
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只股票: {total_time/len(stock_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(stock_codes)
        }
        
    except Exception as e:
        print(f"多线程计算过程中出现错误: {str(e)}")
        raise

# ===== daily update：每日处理函数 =====
def process_daily_industry_indicators(industry_code, target_date):
    """
    处理单个行业的每日指标计算
    
    Args:
        industry_code: 行业代码
        target_date: 目标日期（仅计算这一天的指标）
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该行业在目标日期的旧数据
        delete_sql = f"DELETE FROM industry_ths_index_calc WHERE industry_code = '{industry_code}' AND date = '{target_date}'"
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询该行业最近120天的数据（用于指标计算）
        query = f"""
        SELECT industry_code, date, open, close, high, low, volume, amount
        FROM industry_ths_index
        WHERE industry_code = '{industry_code}'
        AND date <= '{target_date}'
        ORDER BY date DESC
        LIMIT 200
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {industry_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"行业 {industry_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                if df_stock.iloc[i]['date'] == target_date:  # latest date
                # if str(df_stock.iloc[i]['date']) == str(target_date):  # 【1-指定日期计算】
                    row_data = {
                        'industry_code': industry_code,
                        'date': df_stock.iloc[i]['date'],
                        'ma3': None,
                        'ma5': None,
                        'ma10': None,
                        'ma20': None,
                        'ma30': None,
                        'ma60': None,
                        'ma90': None,
                        'ma120': None,
                        'ma200': None,
                        'atr3': None,
                        'atr5': None,
                        'atr10': None,
                        'atr14': None,
                        'growth_streak_days': None,
                        'growth_streak_pct': None
                    }
                    calc_data.append(row_data)
            
            if calc_data:
                # 转换为DataFrame
                df_calc = pd.DataFrame(calc_data)
                
                # 存储到数据库（使用append模式）
                df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                              index=False, method='multi')
                
                # print(f"行业 {industry_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
                return True
            else:
                return False
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)
        
        # 计算连涨天数和连涨幅度
        growth_streak_results = calculate_growth_streak(df_stock)
        
        # 准备插入数据（只插入目标日期的数据）
        calc_data = []
        for i in range(len(df_stock)):
            if df_stock.iloc[i]['date'] == target_date: # latest date
            # if str(df_stock.iloc[i]['date']) == str(target_date): # 【1-指定日期计算】
                row_data = {
                    'industry_code': industry_code,
                    'date': df_stock.iloc[i]['date'],
                }
                
                # 添加MA数据
                for ma_col, ma_values in ma_results.items():
                    row_data[ma_col] = ma_values[i]
                
                # 添加ATR数据
                for atr_col, atr_values in atr_results.items():
                    row_data[atr_col] = atr_values[i]
                
                # 添加连涨天数和连涨幅度
                row_data['growth_streak_days'] = growth_streak_results['growth_streak_days'][i]
                row_data['growth_streak_pct'] = growth_streak_results['growth_streak_pct'][i]
                
                calc_data.append(row_data)
        
        if not calc_data:
            print(f"行业 {industry_code} 在目标日期 {target_date} 没有数据")
            return False
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        # print(f"行业 {industry_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理行业 {industry_code} 时出现错误: {str(e)}")
        return False

def daily_process_industry_indicators(max_workers=10):
    """
    每日处理函数：更新当天全部个股的指标数据
    
    功能说明：
    1. 获取industry_ths_index表中的最新日期
    2. 获取该日期所有有数据的行业代码
    3. 为每个行业获取最近120天的数据（用于指标计算）
    4. 计算这些行业的最新指标（仅最新日期）
    5. 将计算结果存入industry_ths_index_calc表
    
    Args:
        max_workers: 最大线程数，默认为10
        
    Returns:
        dict: 包含处理结果的统计信息
    """
    try:
        print("==== 每日指标计算处理 industry_ths_index_calc ====")
        print("开始每日指标计算处理...")
        
        # latest_date = '2026-04-01'  # 【1-指定日期计算】

        # 获取最新日期
        latest_date_query = "SELECT MAX(date) as latest_date FROM industry_ths_index"
        latest_date_df = pd.read_sql(latest_date_query, engine)
        latest_date = latest_date_df.iloc[0]['latest_date']
        
        if latest_date is None:
            print("未找到有效日期数据，请先更新industry_ths_index表")
            return None
            
        print(f"最新数据日期: {latest_date}")
        
        # 获取该日期所有有数据的股票代码
        industry_codes_query = f"""
        SELECT DISTINCT industry_code 
        FROM industry_ths_index 
        WHERE date = '{latest_date}'
        """
        industry_codes_df = pd.read_sql(industry_codes_query, engine)
        industry_codes = industry_codes_df['industry_code'].tolist()
        
        print(f"共找到 {len(industry_codes)} 只行业在 {latest_date} 有数据")
        
        if not industry_codes:
            print("未找到任何行业数据")
            return None
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_industry = {executor.submit(process_daily_industry_indicators, industry_code, latest_date): industry_code 
                             for industry_code in industry_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(industry_codes)
            processed = 0
            
            for future in as_completed(future_to_industry):
                industry_code = future_to_industry[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'行业 {industry_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 行业 {industry_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"\n每日处理完成！日期: {latest_date}")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票")
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只行业: {total_time/len(industry_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(industry_codes)
        }
        
    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise


if __name__ == "__main__":
    # -------------------- 个股指标计算 --------------------

    # 全量数据计算
    # all_stock_query = f"""
    #  SELECT DISTINCT stock_code FROM stock_daily_qfq WHERE date = (select MAX(date) from stock_daily_qfq) 
    # """
    # all_stock_df = pd.read_sql(all_stock_query, engine)
    # all_stock = all_stock_df['stock_code'].tolist()
    
    # # 测试多线程批量计算
    # calculate_stock_indicators_multithreaded(all_stock, max_workers=10)
    
    # 测试每日处理功能
    daily_process_stock_indicators(max_workers=10)

    # -------------------- 行业指标计算 --------------------

    # 全量数据计算
    # all_stock_query = f"""
    #  SELECT DISTINCT industry_code FROM industry_ths_index WHERE date = (select MAX(date) from industry_ths_index) 
    # """
    # all_stock_df = pd.read_sql(all_stock_query, engine)
    # all_stock = all_stock_df['industry_code'].tolist()
    
    # 测试多线程批量计算
    # calculate_industry_indicators_multithreaded(all_stock, max_workers=10)

    daily_process_industry_indicators(max_workers=10)
