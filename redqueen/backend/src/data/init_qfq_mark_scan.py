"""一次性标记脚本：扫描近 250 个交易日内发生除权 / 权益基准重置的个股

数据源    : stock_daily_qfq（仅读取，不修改）
目标表    : stock_qfq_mark
执行方式  : 一次性手动执行，不纳入循环调度
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(_HERE))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:
    from src.utils.config import settings  # type: ignore
except Exception:
    settings = None


# ---------------------------------------------------------------------------
# 常量 & 数据库连接
# ---------------------------------------------------------------------------
EPS = 0.5                      # 浮点容差（百分点）。normal diff 约 0.001~0.005，除权日通常 >5
SCAN_TRADE_DAYS = 250          # 回溯交易日数
WINDOW_READ_DAYS = 251         # 实际读取：比扫描周期多 1 个交易日，用于识别新股上市首日
CHANGE_RATE_MULTIPLIER = 100.0 # 数据源的 change_rate 按百分值存储（如 5.2 表示 5.2%）


def _build_engine():
    if settings is not None:
        user = settings.DB_USER
        password = settings.DB_PASSWORD
        host = settings.DB_HOST
        port = getattr(settings, "DB_PORT", 3306)
        database = settings.DB_NAME
    else:
        raise RuntimeError("未能加载 settings 配置，请确保 backend 目录在 PYTHONPATH 中")
    url = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        f"?charset=utf8mb4"
    )
    return create_engine(url)


engine = _build_engine()


# ---------------------------------------------------------------------------
# 建表 & DDL
# ---------------------------------------------------------------------------
def ensure_target_table() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS stock_qfq_mark (
      stock_code VARCHAR(10) NOT NULL COMMENT '股票代码（一只股票仅保留一行）',
      last_ex_date DATE DEFAULT NULL COMMENT '250 日扫描区间内最后一次除权/权益重置日',
      init_mark_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        COMMENT '本次初始化扫描标记入库时间',
      last_refresh_qfq DATETIME DEFAULT NULL
        COMMENT '第三方前复权数据上次全量覆盖分析表的执行时间',
      PRIMARY KEY (stock_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COMMENT '前复权扫描标记表：记录存在除权除息事件的个股';
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


# ---------------------------------------------------------------------------
# 业务查询
# ---------------------------------------------------------------------------
def _get_latest_trading_day() -> Optional[str]:
    sql = "SELECT MAX(date) AS d FROM stock_daily_qfq"
    with engine.begin() as conn:
        row = conn.execute(text(sql)).mappings().first()
    if row is None or row["d"] is None:
        return None
    d = row["d"]
    if isinstance(d, pd.Timestamp):
        return d.strftime("%Y-%m-%d")
    return pd.to_datetime(d).strftime("%Y-%m-%d")


def _get_scan_window_endpoints(latest_date: str, n_days: int) -> Tuple[str, str]:
    """
    返回 (end_date, start_date)：[start_date, end_date] 含 end_date 共 n_days 个交易日。
    为识别新股上市首日，实际后续会再向前多读 1 个交易日（共 WINDOW_READ_DAYS = 251）。
    """
    sql = text(
        "SELECT DISTINCT date FROM stock_daily_qfq "
        "WHERE date <= :latest ORDER BY date DESC LIMIT :n"
    )
    df = pd.read_sql(sql, engine, params={"latest": latest_date, "n": n_days})
    if df.empty:
        raise RuntimeError("stock_daily_qfq 无有效交易日数据，无法构建扫描窗口")
    dates = sorted(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").tolist())
    return dates[-1], dates[0]


def _load_latest_rows_per_stock(latest_date: str, per_stock_rows: int) -> pd.DataFrame:
    """
    对每只股票取 <= per_stock_rows 行"不晚于 latest_date 的最近 N 个交易日"，
    以避免因停牌造成固定日期区间对某些股票行数不足/错位。
    """
    # 一次性拉取足够宽的数据；再按 stock_code 降序取最近 per_stock_rows 行。
    # 日期区间取 latest_date 向前约 1.5 年的交易日，保证任意股票都能覆盖 251 行。
    margin_days = 400
    start_date_cutoff = (pd.to_datetime(latest_date) - pd.Timedelta(days=margin_days)) \
        .strftime("%Y-%m-%d")

    sql = text(
        "SELECT stock_code, date, close, change_rate "
        "FROM stock_daily_qfq "
        "WHERE date BETWEEN :start AND :end "
        "ORDER BY stock_code, date DESC"
    )
    df = pd.read_sql(
        sql, engine,
        params={"start": start_date_cutoff, "end": latest_date}
    )
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])

    # 每只股票仅保留最新 per_stock_rows 行
    df = df.sort_values(["stock_code", "date"], ascending=[True, False]) \
           .groupby("stock_code", sort=True, as_index=False) \
           .head(per_stock_rows) \
           .reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# 核心判定
# ---------------------------------------------------------------------------
def _is_ipolike_window(row_count: int, read_days: int) -> bool:
    """新股上市首日判定（基于扫描周期内『是否填满 251 行』来识别）。

    - 扫描周期仍为 250 个交易日；读取时向前多读 1 日，共 WINDOW_READ_DAYS = 251 行。
    - 若某股在 251 日窗口内实际行数 N <= 250，说明窗口最早的那一天就是上市日，
      该日期自身不参与『除权/权益重置』判定，从扫描中剔除。
    - 若 N == 251，说明扫描周期之前仍有历史交易，周期内无上市点，正常扫描。
    """
    return row_count <= (read_days - 1)  # read_days == WINDOW_READ_DAYS == 251


def _scan_one_stock(df_stock: pd.DataFrame, read_days: int) -> Optional[str]:
    """
    单股扫描：返回最后一次（距离最新交易日最近的一次）『疑似除权/权益重置』日期。

    关键对齐约定：
      - 行按 date 降序：row[0] 最新，row[1] 次新，...
      - row[i-1].change_rate 字段，行业口径 = (close_{i-1} / close_i − 1) × 100
      - manual_pct 也按同式计算，比较的就是 row[i-1] 这一天的合理性。
      - diff > EPS ⇒ 除权/权益重置发生在 row[i-1]，last_ex_date = row[i-1].date
      - diff ≤ EPS ⇒ 正常交易日，继续向前扫描。

    扫描上限：
      - N == 251：共做 250 次相邻比较（覆盖近 250 个交易日）；
      - N <= 250：最早一天为上市日，最多扫描 (N-1) 次。
    """
    last_ex_date: Optional[str] = None

    df_sorted = df_stock.sort_values("date", ascending=False, kind="mergesort") \
                        .reset_index(drop=True)
    row_count = len(df_sorted)
    if row_count < 2:
        return None

    first_row_is_ipo = _is_ipolike_window(row_count, read_days)

    # 相邻比较次数上限
    if first_row_is_ipo:
        max_compares = row_count - 1
    else:
        max_compares = read_days - 1  # 251 → 250

    compares_done = 0
    # i 从 1 开始；每次循环里 row[i-1] = "较新的那一天"，row[i] = "更前一天"
    for i in range(1, row_count):
        newer_row = df_sorted.iloc[i - 1]   # 较新日：本次比较的"归属日"
        older_row = df_sorted.iloc[i]       # 更旧日：作分母

        # 数据有效性校验
        try:
            newer_close = float(newer_row["close"])
        except (TypeError, ValueError):
            newer_close = None
        try:
            older_close = float(older_row["close"])
        except (TypeError, ValueError):
            older_close = None
        try:
            newer_change_rate = (
                float(newer_row["change_rate"])
                if newer_row["change_rate"] is not None else None
            )
        except (TypeError, ValueError):
            newer_change_rate = None

        # 两端 close 必须合法；否则跳过本行比较，锚点推进为 row[i-1]
        if (newer_close is None or pd.isna(newer_close) or newer_close <= 0
                or older_close is None or pd.isna(older_close) or older_close <= 0):
            compares_done += 1
            if compares_done >= max_compares:
                break
            continue

        # change_rate 缺失：无法判定本行，跳过，但锚点推进到 row[i-1]
        if newer_change_rate is None or pd.isna(newer_change_rate):
            compares_done += 1
            if compares_done >= max_compares:
                break
            continue

        # 手动计算 newer_row 那一天的涨跌幅
        try:
            manual_pct = (newer_close / older_close - 1.0) * CHANGE_RATE_MULTIPLIER
        except (FloatingPointError, ZeroDivisionError, OverflowError):
            print(f"  [WARN] 浮点异常跳过: stock={newer_row['stock_code']} "
                  f"date={newer_row['date']} close={newer_close} prev_close={older_close}")
            compares_done += 1
            if compares_done >= max_compares:
                break
            continue

        diff = abs(manual_pct - newer_change_rate)

        if diff <= EPS:
            # 正常交易日：继续向前
            compares_done += 1
            if compares_done >= max_compares:
                break
            continue

        # diff > EPS：权益基准重置发生在较新日 newer_row.date
        # 因为是由新→旧遍历，首次命中就是"最新一次除权"，直接返回
        last_ex_date = pd.to_datetime(newer_row["date"]).strftime("%Y-%m-%d")
        return last_ex_date

    return last_ex_date


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def _upsert_mark(rows: list) -> None:
    """整表清空后，重新写入本轮所有命中跳空的股票。

    语义：
      - stock_qfq_mark 仅记录本扫描周期内"存在除权/权益重置"的股票，
        不再保留历史未命中记录。
      - 外部脚本（fetch_kline_to_analysis / calc_hl_mid 等）只需判断
        "某股票是否在本表中"来决定是否走全量刷新 / 全量重算路径。
    """
    if not rows:
        # 本轮没有命中：表内旧数据也应清空，避免历史残留被误当成本轮信号
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM stock_qfq_mark"))
        return

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM stock_qfq_mark"))

        conn.execute(
            text(
                "INSERT INTO stock_qfq_mark (stock_code, last_ex_date, init_mark_time) "
                "VALUES (:code, :d, NOW())"
            ),
            [{"code": r["stock_code"], "d": r["last_ex_date"]} for r in rows],
        )


def _load_last_two_days(latest_date: str) -> pd.DataFrame:
    """取每只股票最新两天的收盘数据（只读，不修改 source 表）。

    返回字段：stock_code, date, close, change_rate
    """
    margin_days = 15
    start_date_cutoff = (pd.to_datetime(latest_date) - pd.Timedelta(days=margin_days)) \
        .strftime("%Y-%m-%d")

    sql = text(
        "SELECT stock_code, date, close, change_rate "
        "FROM stock_daily_qfq "
        "WHERE date BETWEEN :start AND :end "
        "ORDER BY stock_code, date DESC"
    )
    df = pd.read_sql(
        sql, engine,
        params={"start": start_date_cutoff, "end": latest_date}
    )
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])

    # 每只股票只保留最新 2 行
    df = df.sort_values(["stock_code", "date"], ascending=[True, False]) \
           .groupby("stock_code", sort=True, as_index=False) \
           .head(2) \
           .reset_index(drop=True)
    return df


def _scan_one_stock_incremental(df_stock: pd.DataFrame) -> Optional[str]:
    """增量判定：比较『最新日 vs 前一日』，返回最新日是否触发跳空/除权。

    - df_stock 应包含最新两日的行，date 降序；
    - 仅比较 row[0]（最新日） 与 row[1]（前一日）；
    - 行数 < 2 或 close/change_rate 无效 → 跳过；
    - 若最新日本身为该股票的首日（行数=1 或没有更多历史）：
      因无法判定"跳空"，视作正常，跳过。
    """
    if df_stock is None or len(df_stock) < 2:
        return None

    df_sorted = df_stock.sort_values("date", ascending=False, kind="mergesort") \
                        .reset_index(drop=True)

    newer_row = df_sorted.iloc[0]
    older_row = df_sorted.iloc[1]

    try:
        newer_close = float(newer_row["close"])
        older_close = float(older_row["close"])
        newer_change_rate = (
            float(newer_row["change_rate"])
            if newer_row["change_rate"] is not None else None
        )
    except (TypeError, ValueError):
        return None

    if (newer_close is None or pd.isna(newer_close) or newer_close <= 0
            or older_close is None or pd.isna(older_close) or older_close <= 0):
        return None
    if newer_change_rate is None or pd.isna(newer_change_rate):
        return None

    try:
        manual_pct = (newer_close / older_close - 1.0) * CHANGE_RATE_MULTIPLIER
    except (FloatingPointError, ZeroDivisionError, OverflowError):
        print(f"  [WARN] 浮点异常跳过（增量）: stock={newer_row['stock_code']} "
              f"date={newer_row['date']}")
        return None

    diff = abs(manual_pct - newer_change_rate)
    if diff <= EPS:
        return None

    return pd.to_datetime(newer_row["date"]).strftime("%Y-%m-%d")


def run_incremental(batch_size: int = 500) -> dict:
    """增量扫描入口：对 stock_daily_qfq 中全部个股的『最新日 vs 前一日』做一次判定，

    命中跳空/除权 → 整表清空后，写入本轮所有命中股票。
    """
    t0 = time.time()
    print("=" * 72)
    print(f"[{datetime.now():%H:%M:%S}] 『stock_qfq_mark 增量扫描』 启动")
    print("=" * 72)

    # 建表（幂等）
    ensure_target_table()

    latest_day = _get_latest_trading_day()
    if latest_day is None:
        print("stock_daily_qfq 无数据，直接退出。")
        return {"rows_read": 0, "marked_stocks": 0, "elapsed_sec": 0.0}

    print(f"  最新交易日   : {latest_day}")

    print(f"  读取 stock_daily_qfq（每只股票取最近 2 行） ... ", end="", flush=True)
    df_all = _load_last_two_days(latest_day)
    n_stocks = 0 if df_all.empty else df_all["stock_code"].nunique()
    print(f"共 {len(df_all)} 行  {n_stocks} 只股票，耗时 {time.time() - t0:.2f}s")

    if df_all.empty:
        print("源表无数据，结束。")
        return {"rows_read": 0, "marked_stocks": 0, "elapsed_sec": time.time() - t0}

    stock_group = df_all.groupby("stock_code", sort=True)
    total_stocks = len(stock_group)
    processed = 0
    marked_buffer: list = []
    total_marked = 0
    skipped_stocks = 0

    for stock_code, grp in stock_group:
        try:
            last_ex = _scan_one_stock_incremental(grp)
        except Exception as exc:
            print(f"  [ERROR] 股票 {stock_code} 增量扫描异常：{exc}，跳过")
            skipped_stocks += 1
            processed += 1
            continue

        if last_ex is not None:
            marked_buffer.append({
                "stock_code": stock_code,
                "last_ex_date": last_ex,
            })

        processed += 1
        if len(marked_buffer) >= batch_size:
            _upsert_mark(marked_buffer)
            total_marked += len(marked_buffer)
            marked_buffer = []
            print(f"\r[{datetime.now():%H:%M:%S}] "
                  f"进度 {processed}/{total_stocks} 已标记 {total_marked} 只 跳过 {skipped_stocks} 只",
                  end="", flush=True)

    if marked_buffer:
        _upsert_mark(marked_buffer)
        total_marked += len(marked_buffer)
        marked_buffer = []

    print("")
    print(f"[{datetime.now():%H:%M:%S}] 增量扫描完成，总耗时 {time.time() - t0:.2f}s")
    print(f"  扫描股票数  : {total_stocks}")
    print(f"  标记股票数  : {total_marked}")
    print(f"  跳过/异常   : {skipped_stocks}")

    return {
        "rows_read": len(df_all),
        "total_stocks": total_stocks,
        "marked_stocks": total_marked,
        "skipped_stocks": skipped_stocks,
        "latest_trade_day": latest_day,
        "elapsed_sec": time.time() - t0,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_once(batch_size: int = 500) -> dict:
    t0 = time.time()
    print("=" * 72)
    print(f"[{datetime.now():%H:%M:%S}] 『stock_qfq_mark 初始化扫描』 启动")
    print("=" * 72)

    # 1) 建表（幂等）
    ensure_target_table()

    # 2) 确定最新交易日；按每只股票取最近 WINDOW_READ_DAYS = 251 行，避免停牌导致的日期错位
    latest_day = _get_latest_trading_day()
    if latest_day is None:
        print("stock_daily_qfq 无数据，直接退出。")
        return {"rows_read": 0, "marked_stocks": 0, "elapsed_sec": 0.0}

    print(f"  最新交易日   : {latest_day}")
    print(f"  每只股票取最近 {WINDOW_READ_DAYS} 行（回溯 ~400 自然日），"
          f"N <= 250 → 最早一行为上市日，不参与判定")

    # 3) 读取源数据（只读）— 每只股票固定取最新 251 个交易日
    print(f"  读取 stock_daily_qfq ... ", end="", flush=True)
    df_all = _load_latest_rows_per_stock(latest_day, WINDOW_READ_DAYS)
    n_stocks = 0 if df_all.empty else df_all["stock_code"].nunique()
    print(f"共 {len(df_all)} 行  {n_stocks} 只股票，耗时 {time.time() - t0:.2f}s")

    if df_all.empty:
        print("源表扫描区间无数据，结束。")
        return {"rows_read": 0, "marked_stocks": 0, "elapsed_sec": time.time() - t0}

    # 4) 逐股扫描（按 stock_code 分组，_scan_one_stock 内部按 date 降序遍历）
    stock_group = df_all.groupby("stock_code", sort=True)
    total_stocks = len(stock_group)
    processed = 0
    marked_buffer: list = []
    total_marked = 0
    skipped_stocks = 0

    for stock_code, grp in stock_group:
        try:
            last_ex = _scan_one_stock(grp, WINDOW_READ_DAYS)
        except Exception as exc:
            print(f"  [ERROR] 股票 {stock_code} 扫描异常：{exc}，跳过")
            skipped_stocks += 1
            processed += 1
            continue

        if last_ex is not None:
            marked_buffer.append({
                "stock_code": stock_code,
                "last_ex_date": last_ex,
            })

        processed += 1
        if len(marked_buffer) >= batch_size:
            _upsert_mark(marked_buffer)
            total_marked += len(marked_buffer)
            marked_buffer = []
            print(f"\r[{datetime.now():%H:%M:%S}] "
                  f"进度 {processed}/{total_stocks} 已标记 {total_marked} 只 跳过 {skipped_stocks} 只",
                  end="", flush=True)

    # 处理剩余缓冲
    if marked_buffer:
        _upsert_mark(marked_buffer)
        total_marked += len(marked_buffer)
        marked_buffer = []

    print("")
    print(f"[{datetime.now():%H:%M:%S}] 扫描完成，总耗时 {time.time() - t0:.2f}s")
    print(f"  扫描股票数  : {total_stocks}")
    print(f"  标记股票数  : {total_marked}")
    print(f"  跳过/异常   : {skipped_stocks}")

    return {
        "rows_read": len(df_all),
        "total_stocks": total_stocks,
        "marked_stocks": total_marked,
        "skipped_stocks": skipped_stocks,
        "latest_trade_day": latest_day,
        "window_rows_per_stock": WINDOW_READ_DAYS,
        "elapsed_sec": time.time() - t0,
    }


if __name__ == "__main__":
 
    # 全量扫描  
    # stats = run_once(batch_size=500)

    # # 增量扫描  
    stats = run_incremental(batch_size=500)

    print("完成，统计信息:", stats)
