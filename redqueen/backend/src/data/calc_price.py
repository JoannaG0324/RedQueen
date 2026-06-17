"""
股票技术指标计算模块

功能概述：
- 计算个股和行业的技术指标，包括移动平均线(MA)、平均真实波幅(ATR)、成交量变化率(volume_pct)、
  多周期涨跌幅(chg_pct_3/5/20)、连涨天数/幅度(growth_streak)
- 支持两种计算模式：增量更新（每日）和全量重算（覆盖）

计算逻辑说明：
1. 所有计算函数统一使用 "date 升序" 进行计算，结果按 "date 降序" 返回
2. 数据量不足时对应指标为 NaN，上游填充 None（由 DataFrame to_dict('records') 统一处理）
3. 增量模式：读取最近 INCREMENTAL_WINDOW(250) 天数据，仅计算并插入目标日期的数据
4. 全量模式：读取最多 FULL_RECALC_LIMIT(4000) 天数据，删除旧数据后重新计算并覆盖

指标列表：
- MA系列：ma3, ma5, ma10, ma20, ma30, ma60, ma90, ma120, ma200（移动平均线）
- ATR系列：atr3, atr5, atr10, atr14（平均真实波幅）
- volume_pct：每日成交量较前一交易日的变化率（%）
- chg_pct_3/5/20：每日收盘价较3/5/20日前收盘价的涨跌幅（%）
- growth_streak_days：连涨天数
- growth_streak_pct：连涨期间累计涨幅（%）

数据表配置：
- 个股数据：SOURCE_TABLE(stock_daily_analysis) -> TARGET_TABLE(stock_daily_qfq_calc)
- 行业数据：INDUSTRY_SOURCE_TABLE(industry_ths_index) -> INDUSTRY_TARGET_TABLE(industry_ths_index_calc)
- 标记表：MARK_TABLE(stock_qfq_mark)，用于标记跳空/除权股票，触发全量重算

主要函数：
- daily_process_stock_indicators(max_workers=10, full_recalc=False, stock_codes=None)
  个股指标每日处理，支持增量/全量模式
- daily_process_industry_indicators(max_workers=10, full_recalc=False, industry_codes=None)
  行业指标每日处理，支持增量/全量模式

使用示例：
    # 每日增量更新（默认）
    daily_process_stock_indicators(max_workers=10)
    daily_process_industry_indicators(max_workers=10)
    
    # 全量重算所有数据
    daily_process_stock_indicators(max_workers=10, full_recalc=True)
    daily_process_industry_indicators(max_workers=10, full_recalc=True)
    
    # 全量重算指定股票/行业
    daily_process_stock_indicators(max_workers=10, full_recalc=True, stock_codes=["000001"])
    daily_process_industry_indicators(max_workers=10, full_recalc=True, industry_codes=["SW101"])
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sqlalchemy import create_engine, text
import numpy as np
import pandas as pd
try:
    from src.utils.config import settings
except ImportError:
    from utils.config import settings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 数据库连接配置
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

# 数据源与目标表配置（个股）
SOURCE_TABLE = "stock_daily_analysis"          # 行情数据源（前复权日线）
TARGET_TABLE = "stock_daily_qfq_calc"              # 指标计算结果表
MARK_TABLE = "stock_qfq_mark"                    # 标记表，用于跟踪全量/增量

# 创建数据库连接
engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

# ==================== 计算参数 ====================
MA_PERIODS = [3, 5, 10, 20, 30, 60, 90, 120, 200]
ATR_PERIODS = [3, 5, 10, 14]
CHG_PCT_PERIODS = [3, 5, 20]

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


def calculate_volume_pct(df):
    """计算每日成交量较前一交易日的变化率。"""
    if df is None or len(df) == 0:
        return {"volume_pct": []}

    asc = _to_asc(df)
    volume = asc["volume"].astype(float).values
    n = len(volume)

    prev_volume = np.roll(volume, 1)
    prev_volume[0] = np.nan

    with np.errstate(divide="ignore", invalid="ignore"):
        volume_pct = np.where(prev_volume != 0,
                              (volume - prev_volume) / prev_volume * 100.0, np.nan)

    return {"volume_pct": _fill_none_list(volume_pct[::-1])}


def calculate_chg_pct(df, periods=[3, 5, 20]):
    """计算多周期涨跌幅：close较N日前close的涨跌幅。"""
    if df is None or len(df) == 0:
        return {f"chg_pct_{p}": [] for p in periods}

    asc = _to_asc(df)
    close = asc["close"].astype(float).values
    n = len(close)
    out = {}

    for p in periods:
        if p <= 0 or n <= p:
            chg_pct = np.full(n, np.nan)
        else:
            prev_close = np.roll(close, p)
            prev_close[:p] = np.nan
            with np.errstate(divide="ignore", invalid="ignore"):
                chg_pct = np.where(prev_close != 0,
                                   (close - prev_close) / prev_close * 100.0, np.nan)
        out[f"chg_pct_{p}"] = _fill_none_list(chg_pct[::-1])

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
                "volume_pct": None,
                "chg_pct_3": None, "chg_pct_5": None, "chg_pct_20": None,
                "growth_streak_days": None, "growth_streak_pct": None,
            })
        return rows

    ma_results = calculate_moving_averages(df_stock)
    atr_results = calculate_atr(df_stock)
    volume_pct_results = calculate_volume_pct(df_stock)
    chg_pct_results = calculate_chg_pct(df_stock, periods=[3, 5, 20])
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
        row["volume_pct"] = (
            volume_pct_results["volume_pct"][i]
            if i < len(volume_pct_results["volume_pct"])
            else None
        )
        for chg_col, chg_values in chg_pct_results.items():
            row[chg_col] = chg_values[i] if i < len(chg_values) else None
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


def _bulk_insert_rows(rows, batch_size=500, max_retries=3):
    """按批插入或更新，避免单次 SQL 参数过多。使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 UPSERT。
    
    遇到死锁错误时自动重试，最多重试 max_retries 次。
    """
    if not rows:
        return
    placeholders = (
        ":stock_code, :date, "
        ":ma3, :ma5, :ma10, :ma20, :ma30, :ma60, :ma90, :ma120, :ma200, "
        ":atr3, :atr5, :atr10, :atr14, "
        ":volume_pct, "
        ":chg_pct_3, :chg_pct_5, :chg_pct_20, "
        ":growth_streak_days, :growth_streak_pct"
    )
    cols = (
        "stock_code, date, "
        "ma3, ma5, ma10, ma20, ma30, ma60, ma90, ma120, ma200, "
        "atr3, atr5, atr10, atr14, "
        "volume_pct, "
        "chg_pct_3, chg_pct_5, chg_pct_20, "
        "growth_streak_days, growth_streak_pct"
    )
    update_clause = (
        "ma3 = VALUES(ma3), ma5 = VALUES(ma5), ma10 = VALUES(ma10), "
        "ma20 = VALUES(ma20), ma30 = VALUES(ma30), ma60 = VALUES(ma60), "
        "ma90 = VALUES(ma90), ma120 = VALUES(ma120), ma200 = VALUES(ma200), "
        "atr3 = VALUES(atr3), atr5 = VALUES(atr5), atr10 = VALUES(atr10), atr14 = VALUES(atr14), "
        "volume_pct = VALUES(volume_pct), "
        "chg_pct_3 = VALUES(chg_pct_3), chg_pct_5 = VALUES(chg_pct_5), chg_pct_20 = VALUES(chg_pct_20), "
        "growth_streak_days = VALUES(growth_streak_days), growth_streak_pct = VALUES(growth_streak_pct)"
    )
    ins_sql = text(
        f"INSERT INTO {TARGET_TABLE} ({cols}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )
    
    for retry in range(max_retries + 1):
        try:
            with engine.begin() as conn:
                for start in range(0, len(rows), batch_size):
                    conn.execute(ins_sql, rows[start:start + batch_size])
            return
        except Exception as exc:
            if retry < max_retries and hasattr(exc, 'args') and exc.args[0] == 1213:
                time.sleep(0.1 * (retry + 1))
                continue
            raise


def process_stock_indicators_recalc(stock_code):
    """对某只股票进行『全量重算』（stock_qfq_mark 中存在即标记为跳空命中）。

    步骤：
    1. 从 SOURCE_TABLE 读取最多 FULL_RECALC_LIMIT 条日线；
    2. 向量化计算全部交易日的指标；
    3. 返回计算结果（行数据列表），由调用方统一写入。

    返回值：(stock_code, rows) 元组，rows 为计算后的行数据列表，计算失败返回 None。
    """
    try:
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
            return (stock_code, None)

        rows = _calc_rows_for(df_stock, stock_code, dates_filter=None)
        return (stock_code, rows)

    except Exception as exc:
        print(f"  [重算] {stock_code} 计算失败: {exc}")
        return (stock_code, None)


def process_daily_stock_indicators(stock_code, target_date):
    """对某只股票进行『增量更新』，只计算 target_date 这一天的指标。

    按最近 INCREMENTAL_WINDOW 天的行情计算指标，使用 UPSERT（INSERT ... ON DUPLICATE KEY UPDATE）
    写入 target_date 一行，已存在的数据更新，不存在的数据插入。
    """
    try:
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
            return 0

        rows = _calc_rows_for(df_stock, stock_code,
                               dates_filter=[str(target_date)])
        if not rows:
            return 0

        _bulk_insert_rows(rows)
        return len(rows)

    except Exception as exc:
        print(f"  [增量] {stock_code} 失败: {exc}")
        return 0


def daily_process_stock_indicators(max_workers=10, full_recalc=False, stock_codes=None):
    """每日处理函数：按 MARK_TABLE(stock_qfq_mark) 分流为全量重算与增量更新。

    模式说明：
    - 增量模式（full_recalc=False，默认）：
      * MARK_TABLE 中存在的股票（本轮被标记为跳空/除权）走全量重算；
      * 其它股票：对 SOURCE_TABLE 的最新日期做每日增量更新；
    - 全量模式（full_recalc=True）：删除 TARGET_TABLE 中全部数据，重新计算并覆盖全量数据；
    - 数据源全部使用 SOURCE_TABLE（= stock_daily_analysis）。

    Args:
        max_workers: 最大线程数，默认为10
        full_recalc: 是否全量重算，默认为False；设为True时忽略MARK_TABLE，强制全量重算
        stock_codes: 指定股票代码列表，为None时处理全部股票

    Returns:
        dict: 包含处理结果的统计信息
    """
    try:
        print(f"==== 每日指标计算处理 {TARGET_TABLE} ====")
        print(f"数据源: {SOURCE_TABLE}，标记表: {MARK_TABLE}")
        print(f"模式: {'全量重算' if full_recalc else '增量更新'}")

        latest_df = pd.read_sql(
            text(f"SELECT MAX(date) as latest_date FROM {SOURCE_TABLE}"),
            engine,
        )
        latest_date = latest_df.iloc[0]["latest_date"]
        if latest_date is None or pd.isna(latest_date):
            print(f"未在 {SOURCE_TABLE} 中找到有效日期，请先更新；返回 None")
            return None

        print(f"最新数据日期: {latest_date}")

        if stock_codes is None:
            codes_query = text(f"""
                SELECT DISTINCT stock_code FROM {SOURCE_TABLE} WHERE date = :d
            """)
            codes_df = pd.read_sql(codes_query, engine, params={"d": latest_date})
            all_codes = set(codes_df["stock_code"].tolist())
        else:
            if isinstance(stock_codes, str):
                stock_codes = [stock_codes]
            all_codes = set(stock_codes)

        if full_recalc:
            print(f"执行全量重算，共 {len(all_codes)} 只股票")
            recalc_codes = list(all_codes)
            incremental_codes = []
        else:
            try:
                mark_df = pd.read_sql(text(f"""
                    SELECT DISTINCT stock_code FROM {MARK_TABLE}
                """), engine)
            except Exception:
                mark_df = pd.DataFrame(columns=["stock_code"])

            if mark_df.empty:
                recalc_codes = set()
            else:
                recalc_codes = set(mark_df["stock_code"].astype(str).tolist())

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
            
            all_results = []
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
                        code, rows = fut.result()
                        all_results.append((code, rows))
                        if rows is not None:
                            print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，{len(rows)} 行", end="", flush=True)
                        else:
                            print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，无数据", end="", flush=True)
                    except Exception as exc:
                        print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，失败: {exc}", end="", flush=True)
                        all_results.append((code, None))
                print()
            
            print("开始串行写入数据库...")
            processed = 0
            total = len(all_results)
            for code, rows in sorted(all_results, key=lambda x: x[0]):
                processed += 1
                if rows is None:
                    stats["recalc_fail"] += 1
                    continue
                try:
                    _bulk_insert_rows(rows)
                    stats["recalc_ok"] += 1
                    print(f"\r[全量模式] 写入完成 {processed}/{total}：{code}，{len(rows)} 行", end="", flush=True)
                except Exception as exc:
                    print(f"\r[全量模式] 写入完成 {processed}/{total}：{code}，失败: {exc}", end="", flush=True)
                    stats["recalc_fail"] += 1
            print()

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
                        row_count = fut.result()
                        if row_count > 0:
                            stats["incr_ok"] += 1
                            print(f"\r[增量模式] 已完成 {processed}/{total}：{code} 成功，写入 {row_count} 行", end="", flush=True)
                        else:
                            stats["incr_fail"] += 1
                    except Exception as exc:
                        print(f"\r[增量模式] 已完成 {processed}/{total}：{code} 失败: {exc}", end="", flush=True)
                        stats["incr_fail"] += 1
                print()

        total_time = time.time() - start_time
        print(f"\n每日处理完成！日期: {latest_date}")
        print("  全量重算:", stats["recalc_ok"], "成功，", stats["recalc_fail"], "失败")
        print("  增量更新:", stats["incr_ok"], "成功，", stats["incr_fail"], "失败")
        print(f"  总耗时: {total_time:.2f} 秒")

        return stats

    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise

# ==================== 【行业数据】处理行业指标并写入数据库 ====================

INDUSTRY_SOURCE_TABLE = "industry_ths_index"
INDUSTRY_TARGET_TABLE = "industry_ths_index_calc"


def _calc_industry_rows_for(df_industry, industry_code, dates_filter=None):
    """通用：在按 date 降序的 df_industry 上计算全部行业指标行。

    若 dates_filter 不为空，则仅保留日期在该列表中的行（通过 str(date) 匹配）。
    """
    n = len(df_industry)
    if n == 0:
        return []

    if n < 3:
        rows = []
        for i in range(n):
            date_i = df_industry.iloc[i]["date"]
            if dates_filter is not None and str(date_i) not in set(dates_filter):
                continue
            rows.append({
                "industry_code": industry_code,
                "date": date_i,
                "ma3": None, "ma5": None, "ma10": None,
                "ma20": None, "ma30": None, "ma60": None,
                "ma90": None, "ma120": None, "ma200": None,
                "atr3": None, "atr5": None, "atr10": None, "atr14": None,
                "volume_pct": None,
                "chg_pct_3": None, "chg_pct_5": None, "chg_pct_20": None,
                "growth_streak_days": None, "growth_streak_pct": None,
            })
        return rows

    ma_results = calculate_moving_averages(df_industry)
    atr_results = calculate_atr(df_industry)
    volume_pct_results = calculate_volume_pct(df_industry)
    chg_pct_results = calculate_chg_pct(df_industry, periods=[3, 5, 20])
    growth_results = calculate_growth_streak(df_industry)

    rows = []
    for i in range(n):
        date_i = df_industry.iloc[i]["date"]
        if dates_filter is not None and str(date_i) not in set(dates_filter):
            continue

        row = {"industry_code": industry_code, "date": date_i}
        for ma_col, ma_values in ma_results.items():
            row[ma_col] = ma_values[i] if i < len(ma_values) else None
        for atr_col, atr_values in atr_results.items():
            row[atr_col] = atr_values[i] if i < len(atr_values) else None
        row["volume_pct"] = (
            volume_pct_results["volume_pct"][i]
            if i < len(volume_pct_results["volume_pct"])
            else None
        )
        for chg_col, chg_values in chg_pct_results.items():
            row[chg_col] = chg_values[i] if i < len(chg_values) else None
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


def _bulk_insert_industry_rows(rows, batch_size=500, max_retries=3):
    """按批插入或更新行业指标数据，避免单次 SQL 参数过多。使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 UPSERT。
    
    遇到死锁错误时自动重试，最多重试 max_retries 次。
    """
    if not rows:
        return
    placeholders = (
        ":industry_code, :date, "
        ":ma3, :ma5, :ma10, :ma20, :ma30, :ma60, :ma90, :ma120, :ma200, "
        ":atr3, :atr5, :atr10, :atr14, "
        ":volume_pct, "
        ":chg_pct_3, :chg_pct_5, :chg_pct_20, "
        ":growth_streak_days, :growth_streak_pct"
    )
    cols = (
        "industry_code, date, "
        "ma3, ma5, ma10, ma20, ma30, ma60, ma90, ma120, ma200, "
        "atr3, atr5, atr10, atr14, "
        "volume_pct, "
        "chg_pct_3, chg_pct_5, chg_pct_20, "
        "growth_streak_days, growth_streak_pct"
    )
    update_clause = (
        "ma3 = VALUES(ma3), ma5 = VALUES(ma5), ma10 = VALUES(ma10), "
        "ma20 = VALUES(ma20), ma30 = VALUES(ma30), ma60 = VALUES(ma60), "
        "ma90 = VALUES(ma90), ma120 = VALUES(ma120), ma200 = VALUES(ma200), "
        "atr3 = VALUES(atr3), atr5 = VALUES(atr5), atr10 = VALUES(atr10), atr14 = VALUES(atr14), "
        "volume_pct = VALUES(volume_pct), "
        "chg_pct_3 = VALUES(chg_pct_3), chg_pct_5 = VALUES(chg_pct_5), chg_pct_20 = VALUES(chg_pct_20), "
        "growth_streak_days = VALUES(growth_streak_days), growth_streak_pct = VALUES(growth_streak_pct)"
    )
    ins_sql = text(
        f"INSERT INTO {INDUSTRY_TARGET_TABLE} ({cols}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )
    
    for retry in range(max_retries + 1):
        try:
            with engine.begin() as conn:
                for start in range(0, len(rows), batch_size):
                    conn.execute(ins_sql, rows[start:start + batch_size])
            return
        except Exception as exc:
            if retry < max_retries and hasattr(exc, 'args') and exc.args[0] == 1213:
                time.sleep(0.1 * (retry + 1))
                continue
            raise


def process_industry_indicators_recalc(industry_code):
    """对某个行业进行『全量重算』。

    步骤：
    1. 从 INDUSTRY_SOURCE_TABLE 读取最多 FULL_RECALC_LIMIT 条日线；
    2. 向量化计算全部交易日的指标；
    3. 返回计算结果（行数据列表），由调用方统一写入。

    返回值：(industry_code, rows) 元组，rows 为计算后的行数据列表，计算失败返回 None。
    """
    try:
        query = text(f"""
            SELECT industry_code, date, open, close, high, low, volume, amount
            FROM {INDUSTRY_SOURCE_TABLE}
            WHERE industry_code = :code
            ORDER BY date DESC
            LIMIT :lim
        """)
        df_industry = pd.read_sql(query, engine,
                                   params={"code": industry_code, "lim": FULL_RECALC_LIMIT})

        if df_industry.empty:
            print(f"  [重算] {industry_code} 在 {INDUSTRY_SOURCE_TABLE} 无数据，跳过")
            return (industry_code, None)

        rows = _calc_industry_rows_for(df_industry, industry_code, dates_filter=None)
        return (industry_code, rows)

    except Exception as exc:
        print(f"  [重算] {industry_code} 计算失败: {exc}")
        return (industry_code, None)

def process_daily_industry_indicators(industry_code, target_date):
    """对某个行业进行『增量更新』，只计算 target_date 这一天的指标。

    按最近 INCREMENTAL_WINDOW 天的行情计算指标，使用 UPSERT（INSERT ... ON DUPLICATE KEY UPDATE）
    写入 target_date 一行，已存在的数据更新，不存在的数据插入。
    """
    try:
        query = text(f"""
            SELECT industry_code, date, open, close, high, low, volume, amount
            FROM {INDUSTRY_SOURCE_TABLE}
            WHERE industry_code = :code AND date <= :d
            ORDER BY date DESC
            LIMIT :lim
        """)
        df_industry = pd.read_sql(
            query, engine,
            params={"code": industry_code, "d": target_date,
                    "lim": INCREMENTAL_WINDOW},
        )

        if df_industry.empty:
            print(f"  [增量] {industry_code} 在 {INDUSTRY_SOURCE_TABLE} 无数据")
            return 0

        rows = _calc_industry_rows_for(df_industry, industry_code,
                                        dates_filter=[str(target_date)])
        if not rows:
            return 0

        _bulk_insert_industry_rows(rows)
        return len(rows)

    except Exception as exc:
        print(f"  [增量] {industry_code} 失败: {exc}")
        return 0

def daily_process_industry_indicators(max_workers=10, full_recalc=False, industry_codes=None):
    """每日处理函数：按增量或全量模式处理行业指标。

    模式说明：
    - 增量模式（full_recalc=False，默认）：对 SOURCE_TABLE 的最新日期做每日增量更新；
    - 全量模式（full_recalc=True）：删除 TARGET_TABLE 中全部数据，重新计算并覆盖全量数据。

    数据源全部使用 INDUSTRY_SOURCE_TABLE（= industry_ths_index）。

    Args:
        max_workers: 最大线程数，默认为10
        full_recalc: 是否全量重算，默认为False
        industry_codes: 指定行业代码列表，为None时处理全部行业

    Returns:
        dict: 包含处理结果的统计信息
    """
    try:
        print(f"==== 每日指标计算处理 {INDUSTRY_TARGET_TABLE} ====")
        print(f"数据源: {INDUSTRY_SOURCE_TABLE}")
        print(f"模式: {'全量重算' if full_recalc else '增量更新'}")

        if industry_codes is None:
            codes_query = text(f"""
                SELECT DISTINCT industry_code FROM {INDUSTRY_SOURCE_TABLE} 
                WHERE date = (SELECT MAX(date) FROM {INDUSTRY_SOURCE_TABLE})
            """)
            codes_df = pd.read_sql(codes_query, engine)
            all_codes = set(codes_df["industry_code"].tolist())
        else:
            if isinstance(industry_codes, str):
                industry_codes = [industry_codes]
            all_codes = set(industry_codes)

        if not all_codes:
            print("未找到任何行业数据")
            return None

        if full_recalc:
            print(f"执行全量重算，共 {len(all_codes)} 个行业")
            recalc_codes = list(all_codes)
            incremental_codes = []
        else:
            latest_df = pd.read_sql(
                text(f"SELECT MAX(date) as latest_date FROM {INDUSTRY_SOURCE_TABLE}"),
                engine,
            )
            latest_date = latest_df.iloc[0]["latest_date"]
            if latest_date is None or pd.isna(latest_date):
                print(f"未在 {INDUSTRY_SOURCE_TABLE} 中找到有效日期，请先更新；返回 None")
                return None

            print(f"最新数据日期: {latest_date}")
            recalc_codes = []
            incremental_codes = list(all_codes)

        print(f"全量重算 {len(recalc_codes)} 个，增量更新 {len(incremental_codes)} 个")

        start_time = time.time()
        stats = {"recalc_ok": 0, "recalc_fail": 0,
                 "incr_ok": 0, "incr_fail": 0}

        if recalc_codes:
            print(f"开始全量重算 {len(recalc_codes)} 个行业...")
            recalc_workers = max(2, max_workers // 2)
            
            all_results = []
            with ThreadPoolExecutor(max_workers=recalc_workers) as ex:
                future_map = {
                    ex.submit(process_industry_indicators_recalc, c): c
                    for c in recalc_codes
                }
                processed = 0
                total = len(recalc_codes)
                for fut in as_completed(future_map):
                    code = future_map[fut]
                    processed += 1
                    try:
                        code, rows = fut.result()
                        all_results.append((code, rows))
                        if rows is not None:
                            print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，{len(rows)} 行", end="", flush=True)
                        else:
                            print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，无数据", end="", flush=True)
                    except Exception as exc:
                        print(f"\r[全量模式] 计算完成 {processed}/{total}：{code}，失败: {exc}", end="", flush=True)
                        all_results.append((code, None))
                print()
            
            print("开始串行写入数据库...")
            processed = 0
            total = len(all_results)
            for code, rows in sorted(all_results, key=lambda x: x[0]):
                processed += 1
                if rows is None:
                    stats["recalc_fail"] += 1
                    continue
                try:
                    _bulk_insert_industry_rows(rows)
                    stats["recalc_ok"] += 1
                    print(f"\r[全量模式] 写入完成 {processed}/{total}：{code}，{len(rows)} 行", end="", flush=True)
                except Exception as exc:
                    print(f"\r[全量模式] 写入完成 {processed}/{total}：{code}，失败: {exc}", end="", flush=True)
                    stats["recalc_fail"] += 1
            print()

        if incremental_codes:
            print(f"开始增量更新 {len(incremental_codes)} 个行业...")
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {
                    ex.submit(process_daily_industry_indicators, c, latest_date): c
                    for c in incremental_codes
                }
                processed = 0
                total = len(incremental_codes)
                for fut in as_completed(future_map):
                    code = future_map[fut]
                    processed += 1
                    try:
                        row_count = fut.result()
                        if row_count > 0:
                            stats["incr_ok"] += 1
                            print(f"\r[增量模式] 已完成 {processed}/{total}：{code} 成功，写入 {row_count} 行", end="", flush=True)
                        else:
                            stats["incr_fail"] += 1
                    except Exception as exc:
                        print(f"\r[增量模式] 已完成 {processed}/{total}：{code} 失败: {exc}", end="", flush=True)
                        stats["incr_fail"] += 1
                print()

        total_time = time.time() - start_time
        print(f"\n每日处理完成！")
        if not full_recalc:
            print(f"日期: {latest_date}")
        print("  全量重算:", stats["recalc_ok"], "成功，", stats["recalc_fail"], "失败")
        print("  增量更新:", stats["incr_ok"], "成功，", stats["incr_fail"], "失败")
        print(f"  总耗时: {total_time:.2f} 秒")

        return stats

    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise


if __name__ == "__main__":
    # -------------------- 个股指标计算 --------------------

    # 示例1: 每日增量更新（默认模式）
    # daily_process_stock_indicators(max_workers=10)

    # 示例2: 全量重算所有股票（覆盖表全部数据）
    # daily_process_stock_indicators(max_workers=10, full_recalc=True)

    # 示例3: 全量重算指定股票
    daily_process_stock_indicators(max_workers=10, full_recalc=True, stock_codes=["600228"])

    # # 默认执行每日增量更新
    # daily_process_stock_indicators(max_workers=10)

    # -------------------- 行业指标计算 --------------------

    # 示例1: 每日增量更新（默认模式）
    # daily_process_industry_indicators(max_workers=10)

    # 示例2: 全量重算所有行业（覆盖表全部数据）
    # daily_process_industry_indicators(max_workers=10, full_recalc=True)

    # 示例3: 全量重算指定行业
    # daily_process_industry_indicators(max_workers=10, full_recalc=True, industry_codes=["SW101", "SW102"])

    # # 默认执行每日增量更新
    # daily_process_industry_indicators(max_workers=10)
