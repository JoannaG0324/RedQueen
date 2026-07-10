"""
本地滚动高低点计算脚本
======================

数据源: stock_daily_analysis
目标表: stock_daily_calc_update

计算规则：
  1. 按 stock_code 分组独立处理，日线按 date 升序排序
  2. 每行预计算 hl_mid = (high + low) / 2
  3. 滚动窗口：20 / 60 / 90 / 120 个交易日（当前行在内，按K线条数统计）
  4. 周期高点：窗口内 hl_mid 最大值首次出现那一行的 high 与 date
     周期低点：窗口内 hl_mid 最小值首次出现那一行的 low  与 date
  5. 边界:
       ① 个股累计K线数 < 对应窗口长度 → 该周期字段全部 NULL
       ② 当日 high 或 low 为空（停牌） → 该行所有周期指标全部置 NULL
       ③ 同一窗口多个交易日同为极值 → 保留最早出现的那一个
  6. 写入: 对 (stock_code, date) 唯一键使用 ON DUPLICATE KEY UPDATE,
     不 DELETE，不新增重复行。

对外函数（参数命名保持一致）：
  run_full(start_date="2024-06-01", batch_size=200)
      全量：从 start_date 到 stock_daily_analysis 最新交易日，重算并写入。

  run_from_date(start_date, batch_size=200)
      自定义起始日：等价于 run_full(start_date=...)。

  run_incremental(start_date=None, batch_size=200)
      增量：
        ① 若传了 start_date → 从 start_date 到最新交易日（用于补算/重算
           指定区间；因为历史 high/low 不会变，日常一般不需要）；
        ② 否则 → 仅"最新交易日"一天。
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

# 允许以脚本方式运行：把 backend 目录加入 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(_HERE))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:
    from src.utils.config import settings  # type: ignore
except Exception:
    settings = None


# ---------------------------------------------------------------------------
# 数据库连接
# ---------------------------------------------------------------------------
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
# 核心计算
# ---------------------------------------------------------------------------
WINDOWS = [20, 60, 90, 120]

# 计算时需要"往前多取"的历史天数（给窗口留余量）
_HISTORY_MARGIN_DAYS = 365


def _calc_one_stock(df_stock: pd.DataFrame) -> pd.DataFrame:
    """
    对单只股票的 DataFrame 计算所有周期的滚动高低点。

    输入要求: 包含 date, high, low 列。无需预先排序，函数内部升序处理。
    返回:     按升序、index 对齐的 DataFrame，包含 high_Nd / high_Nd_date /
              low_Nd / low_Nd_date 列（N ∈ WINDOWS）。

    实现说明：对每个窗口使用 numpy stride 构造"滚动矩阵"（shape =
              (n - window + 1, window)），再一次性做 argmax/argmin，避免
              Python 层 for 循环，速度从分钟级降到秒级。
    """
    df = df_stock.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", kind="mergesort").reset_index(drop=True)

    # hl_mid = (high + low) / 2
    df["hl_mid"] = (df["high"].astype(float) + df["low"].astype(float)) / 2.0

    # 停牌掩码：high 或 low 为空 → 该行所有周期指标全部置 NULL
    suspend_mask = df["high"].isna() | df["low"].isna()

    hl_mid_arr = np.asarray(df["hl_mid"], dtype=float)
    high_arr = np.asarray(df["high"], dtype=float)
    low_arr = np.asarray(df["low"], dtype=float)
    date_arr = np.asarray(df["date"])
    n = len(df)

    for window in WINDOWS:
        high_col = f"high_{window}d"
        high_date_col = f"high_{window}d_date"
        low_col = f"low_{window}d"
        low_date_col = f"low_{window}d_date"

        # 默认全为 NULL
        df[high_col] = np.nan
        df[high_date_col] = pd.NaT
        df[low_col] = np.nan
        df[low_date_col] = pd.NaT

        if n < window:
            # 边界①：数据不足，该周期全部 NULL
            continue

        # 构造滚动矩阵（n - window + 1 行，window 列）
        # 使用 stride 视图，零拷贝、零分配。
        from numpy.lib.stride_tricks import sliding_window_view  # numpy >= 1.20

        roll = sliding_window_view(hl_mid_arr, window)  # (n-window+1, window)

        # 窗口内出现 NaN（停牌）→ 整行全 NaN 时输出也置 NaN。
        # np.nanargmax/nanargmin 会忽略 NaN，但"整行全 NaN"会抛 ValueError。
        # 为稳定，手动 mask；部分 NaN 由 nanmax/nanmin 自动忽略。
        nan_mask = np.isnan(roll)

        # 最大值首次出现位置（窗口内相对 index）
        # 用 nanmax 取出最大值，再用 (roll == maxval).argmax 得到首次出现。
        with np.errstate(invalid="ignore", all="ignore"):
            maxval = np.nanmax(roll, axis=1)
            minval = np.nanmin(roll, axis=1)

        # 首次出现的相对下标：逐行扫第一个等于极值的位置
        # 构造 (n-window+1, window) 的 bool 矩阵，再用 argmax。
        # 若整行 NaN（any_nan 且全 NaN），则后续会被置 NaN。
        # 注意：np.isnan 与 NaN 比较永远 False，所以 argmax 不会被 NaN 行污染。
        first_max = (roll == maxval[:, None]).argmax(axis=1)
        first_min = (roll == minval[:, None]).argmin(axis=1)

        # 转换为原始数组绝对索引
        rows = np.arange(window - 1, n)  # 目标行的原始 index
        abs_idx_max = rows - (window - 1) + first_max  # = first_max 绝对索引
        abs_idx_min = rows - (window - 1) + first_min

        # 取值：high / low / date
        high_vals = high_arr[abs_idx_max]
        low_vals = low_arr[abs_idx_min]
        high_dates = date_arr[abs_idx_max]
        low_dates = date_arr[abs_idx_min]

        # 整行全 NaN 的窗口 → 输出也置 NaN（避免 nanmax 给出 -inf 之类异常值）
        all_nan = nan_mask.all(axis=1)
        high_vals[all_nan] = np.nan
        low_vals[all_nan] = np.nan

        # 写回 df（只填 rows 行，前 window-1 行保持 NULL）
        df.loc[rows, high_col] = high_vals
        df.loc[rows, low_col] = low_vals
        df.loc[rows, high_date_col] = high_dates
        df.loc[rows, low_date_col] = low_dates

    # 边界②：凡当日停牌者，所有新增字段置空
    calc_cols = []
    for w in WINDOWS:
        calc_cols += [
            f"high_{w}d", f"high_{w}d_date",
            f"low_{w}d",  f"low_{w}d_date",
        ]
    df.loc[suspend_mask, calc_cols] = np.nan

    # 计算 high_20d_last：以每行为基准，往前统计 high_20d 保持不变的天数
    # 例：07-03 high_20d=4.6018，07-02、07-01 也是 4.6018，06-30 不是 → high_20d_last=3
    df["high_20d_last"] = np.nan
    if "high_20d" in df.columns:
        valid_mask = ~df["high_20d"].isna()
        if valid_mask.any():
            # 用 cumsum 标记"值变化"的分组边界
            diff = df["high_20d"].ne(df["high_20d"].shift(1))
            group_id = diff.cumsum()
            # 每个 group 内从 1 开始计数
            df.loc[valid_mask, "high_20d_last"] = df[valid_mask].groupby(group_id[valid_mask]).cumcount() + 1

    # 计算 high_120d_last：以每行为基准，往前统计 high_120d 保持不变的天数
    df["high_120d_last"] = np.nan
    if "high_120d" in df.columns:
        valid_mask_120 = ~df["high_120d"].isna()
        if valid_mask_120.any():
            diff_120 = df["high_120d"].ne(df["high_120d"].shift(1))
            group_id_120 = diff_120.cumsum()
            df.loc[valid_mask_120, "high_120d_last"] = df[valid_mask_120].groupby(group_id_120[valid_mask_120]).cumcount() + 1

    return df


# ---------------------------------------------------------------------------
# 数据库读写
# ---------------------------------------------------------------------------
def ensure_target_table() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS stock_daily_calc_update (
      id BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
      stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
      date DATE NOT NULL COMMENT '计算对应的交易日',

      high_20d  DOUBLE DEFAULT NULL COMMENT '20D窗口均价最高点对应原始最高价',
      high_20d_date  DATE DEFAULT NULL COMMENT '20D均价高点发生交易日',
      low_20d   DOUBLE DEFAULT NULL COMMENT '20D窗口均价最低点对应原始最低价',
      low_20d_date   DATE DEFAULT NULL COMMENT '20D均价低点发生交易日',
      high_20d_last INT DEFAULT NULL COMMENT '20D均价高点连续保持天数（往前统计相同值的天数）',

      high_60d  DOUBLE DEFAULT NULL COMMENT '60D窗口均价最高点对应原始最高价',
      high_60d_date  DATE DEFAULT NULL COMMENT '60D均价高点发生交易日',
      low_60d   DOUBLE DEFAULT NULL COMMENT '60D窗口均价最低点对应原始最低价',
      low_60d_date   DATE DEFAULT NULL COMMENT '60D均价低点发生交易日',

      high_90d  DOUBLE DEFAULT NULL COMMENT '90D窗口均价最高点对应原始最高价',
      high_90d_date  DATE DEFAULT NULL COMMENT '90D均价高点发生交易日',
      low_90d   DOUBLE DEFAULT NULL COMMENT '90D窗口均价最低点对应原始最低价',
      low_90d_date   DATE DEFAULT NULL COMMENT '90D均价低点发生交易日',

      high_120d DOUBLE DEFAULT NULL COMMENT '120D窗口均价最高点对应原始最高价',
      high_120d_date DATE DEFAULT NULL COMMENT '120D均价高点发生交易日',
      low_120d  DOUBLE DEFAULT NULL COMMENT '120D窗口均价最低点对应原始最低价',
      low_120d_date  DATE DEFAULT NULL COMMENT '120D均价低点发生交易日',
      high_120d_last INT DEFAULT NULL COMMENT '120D均价高点连续保持天数（往前统计相同值的天数）',

      calc_time DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '指标计算更新时间',

      PRIMARY KEY (id),
      UNIQUE KEY uk_stock_date (stock_code, date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COMMENT '本地脚本-多周期滚动均价高低点计算结果表';
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


def _format_date(x) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, pd.Timestamp):
        if pd.isna(x):
            return None
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (np.datetime64, datetime)):
        try:
            ts = pd.Timestamp(x)
            if pd.isna(ts):
                return None
            return ts.strftime("%Y-%m-%d")
        except Exception:
            return None
    if isinstance(x, float) and np.isnan(x):
        return None
    return None


def upsert_calc_rows(df_out: pd.DataFrame) -> int:
    """
    使用 INSERT ... ON DUPLICATE KEY UPDATE 写入目标表。
    df_out 需包含: stock_code, date, 以及各周期字段。
    返回写入/更新的行数。
    """
    if df_out is None or df_out.empty:
        return 0

    cols = [
        "stock_code", "date",
        "high_20d", "high_20d_date", "low_20d", "low_20d_date", "high_20d_last",
        "high_60d", "high_60d_date", "low_60d", "low_60d_date",
        "high_90d", "high_90d_date", "low_90d", "low_90d_date",
        "high_120d", "high_120d_date", "low_120d", "low_120d_date", "high_120d_last",
    ]
    rows = []
    for _, r in df_out.iterrows():
        row: dict = {
            "stock_code": r["stock_code"],
            "date": _format_date(r["date"]),
            "high_20d_last": (
                None if pd.isna(r.get("high_20d_last")) else int(r["high_20d_last"])
            ),
            "high_120d_last": (
                None if pd.isna(r.get("high_120d_last")) else int(r["high_120d_last"])
            ),
        }
        for w in WINDOWS:
            for prefix in ("high", "low"):
                col_v = f"{prefix}_{w}d"
                col_d = f"{prefix}_{w}d_date"
                v = r.get(col_v)
                row[col_v] = (
                    None
                    if v is None or (isinstance(v, float) and np.isnan(v))
                    else float(v)
                )
                row[col_d] = _format_date(r.get(col_d))
        rows.append(row)

    if not rows:
        return 0

    col_list = ",".join(cols)
    placeholders = ",".join([f":{c}" for c in cols])
    update_clause = ",".join(
        [f"{c}=VALUES({c})" for c in cols if c not in ("stock_code", "date")]
    )
    sql = (
        f"INSERT INTO stock_daily_calc_update ({col_list}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return len(rows)


# ---------------------------------------------------------------------------
# 辅助：读取最新交易日 & 拉取数据
# ---------------------------------------------------------------------------
def _get_latest_trading_day() -> Optional[datetime]:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT MAX(date) FROM stock_daily_analysis")
            ).scalar()
        if row is None:
            return None
        return pd.to_datetime(row).to_pydatetime()
    except Exception:
        return None


def _get_qfq_hit_stocks() -> set:
    """从 stock_qfq_mark 读取本轮被标记为跳空/除权的全部股票代码。

    - 表中存在 => 该股本轮需要"删除历史计算数据 + 全量重算"；
    - 表中不存在 => 保持原增量行为（只算最新一天）。
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT stock_code FROM stock_qfq_mark")
            ).mappings().all()
    except Exception:
        return set()
    return {r["stock_code"] for r in rows}


def _delete_stocks_from_calc(codes: list) -> int:
    """按 stock_code 批量删除 stock_daily_calc_update 中的历史计算数据。"""
    if not codes:
        return 0
    with engine.begin() as conn:
        # 按代码分批删（规避 IN 过长），500 一组
        deleted = 0
        for i in range(0, len(codes), 500):
            chunk = codes[i:i + 500]
            placeholders = ",".join([f":c{j}" for j in range(len(chunk))])
            params = {f"c{j}": c for j, c in enumerate(chunk)}
            res = conn.execute(
                text(f"DELETE FROM stock_daily_calc_update "
                     f"WHERE stock_code IN ({placeholders})"),
                params,
            )
            try:
                deleted += res.rowcount
            except Exception:
                deleted += 0
        return deleted


def _get_earliest_trading_day() -> Optional[datetime]:
    """从 stock_daily_analysis 读最小交易日（用于全量重算的起始锚点）。"""
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT MIN(date) FROM stock_daily_analysis")
            ).scalar()
        if row is None:
            return None
        return pd.to_datetime(row).to_pydatetime()
    except Exception:
        return None


def _get_earliest_for_codes(codes: list) -> Optional[datetime]:
    """只针对给定股票代码，取 stock_daily_analysis 中它们的 MIN(date)。

    用于跳空命中股的全量重算：只看"这些股票自己有多少历史"，不用整表
    MIN(date)，避免把起算日期拉得过早。
    """
    if not codes:
        return None

    placeholders = ",".join([f":c{i}" for i in range(len(codes))])
    params = {f"c{i}": str(c) for i, c in enumerate(codes)}

    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    f"SELECT MIN(date) as d FROM stock_daily_analysis "
                    f"WHERE stock_code IN ({placeholders})"
                ),
                params,
            ).scalar()
    except Exception:
        return None

    if row is None:
        return None
    return pd.to_datetime(row).to_pydatetime()


def _load_stock_data(read_start: str, read_end: str) -> pd.DataFrame:
    sql = (
        "SELECT stock_code, date, high, low FROM stock_daily_analysis "
        "WHERE date BETWEEN :start AND :end "
        "ORDER BY stock_code, date"
    )
    df = pd.read_sql(text(sql), engine, params={"start": read_start, "end": read_end})
    return df


def _run_inner(start_dt: pd.Timestamp,
               write_start_dt: pd.Timestamp,
               end_date: str,
               batch_size: int,
               mode_label: str,
               only_codes=None,
               exclude_codes=None) -> dict:
    """统一的『读取 → 分组计算 → 分批 upsert』主循环。

    start_dt       用于"读数区间"前推 _HISTORY_MARGIN_DAYS 的锚点；
                   一般等于 write_start_dt。
    write_start_dt 回写区间的起始时间（含）。
    end_date       回写区间的结束日期（含，字符串 YYYY-MM-DD）。
    only_codes     不为 None 时，仅对列表内的股票进行计算（用于跳空命中全量重算）。
    exclude_codes  不为 None 时，跳过列表内的股票（用于避免第二步重复算命中股票）。
    """
    read_start_dt = start_dt - pd.Timedelta(days=_HISTORY_MARGIN_DAYS)
    read_start = read_start_dt.strftime("%Y-%m-%d")

    ensure_target_table()

    t0 = time.time()
    print(f"[{datetime.now():%H:%M:%S}] 读取源表 stock_daily_analysis "
          f"({read_start} ~ {end_date}) ... ")
    df_all = _load_stock_data(read_start, end_date)

    # 可选过滤：只保留 only_codes 里的股票
    if only_codes is not None:
        code_set = set(only_codes)
        df_all = df_all[df_all["stock_code"].isin(code_set)].reset_index(drop=True)
        print(f"    过滤后 {len(df_all)} 行（共 {len(code_set)} 只股票）")

    # 可选过滤：排除 exclude_codes 里的股票
    if exclude_codes is not None:
        excl_set = set(exclude_codes)
        df_all = df_all[~df_all["stock_code"].isin(excl_set)].reset_index(drop=True)
        print(f"    排除 {len(excl_set)} 只后剩余 {len(df_all)} 行")

    print(f"    读取 {len(df_all)} 行，用时 {time.time() - t0:.2f}s")

    if df_all.empty:
        print("源表区间内无数据，结束。")
        return {"rows_read": 0, "rows_written": 0, "stocks": 0}

    df_all["date"] = pd.to_datetime(df_all["date"])

    if write_start_dt == pd.Timestamp(end_date):
        latest_codes = set(df_all[df_all["date"] == end_date]["stock_code"].tolist())
        before_filter = df_all["stock_code"].nunique()
        df_all = df_all[df_all["stock_code"].isin(latest_codes)].reset_index(drop=True)
        after_filter = df_all["stock_code"].nunique()
        if before_filter != after_filter:
            print(f"    过滤最新交易日无数据的股票: {before_filter} -> {after_filter} 只")

    total_stocks = df_all["stock_code"].nunique()
    total_written = 0
    processed = 0

    buffer: list = []
    t_calc = time.time()

    for stock_code, grp in df_all.groupby("stock_code", sort=True):
        try:
            df_calc = _calc_one_stock(grp)
            df_calc["stock_code"] = stock_code
            df_out = df_calc[df_calc["date"] >= write_start_dt].copy()
            if not df_out.empty:
                buffer.append(df_out)
        except Exception as exc:
            print(f"  [WARN] 股票 {stock_code} 计算失败: {exc}")
            continue

        processed += 1
        if len(buffer) >= batch_size:
            out = pd.concat(buffer, ignore_index=True)
            total_written += upsert_calc_rows(out)
            buffer = []
            print(f"\r[{datetime.now():%H:%M:%S}] 进度 {processed}/{total_stocks} "
                  f"已写入 {total_written} 行", end="", flush=True)

    if buffer:
        out = pd.concat(buffer, ignore_index=True)
        total_written += upsert_calc_rows(out)
        buffer = []

    print("")
    print(f"[{datetime.now():%H:%M:%S}] {mode_label}完成，用时 {time.time() - t_calc:.2f}s")
    print(f"  股票数 : {total_stocks}")
    print(f"  写入行 : {total_written}")

    return {
        "rows_read": len(df_all),
        "rows_written": total_written,
        "stocks": total_stocks,
        "elapsed_sec": time.time() - t0,
        "start_date": write_start_dt.strftime("%Y-%m-%d"),
        "end_date": end_date,
        "mode": mode_label,
    }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def run_full(start_date: str = "2024-06-01", batch_size: int = 200) -> dict:
    """全量：从 start_date 到最新交易日，每只股票重算区间内每一天的滚动高低点。"""
    print("=" * 72)
    print("本地滚动高低点计算脚本（全量模式）启动")
    latest = _get_latest_trading_day()
    if latest is None:
        print("stock_daily_analysis 无数据，直接退出。")
        return {"rows_read": 0, "rows_written": 0, "stocks": 0}

    end_date = latest.strftime("%Y-%m-%d")
    start_dt = pd.to_datetime(start_date)
    write_start_dt = start_dt

    print(f"  数据源   : stock_daily_analysis")
    print(f"  目标表   : stock_daily_calc_update")
    print(f"  日期区间 : {start_date} ~ {end_date}")
    print(f"  滚动窗口 : {WINDOWS}")
    print("=" * 72)

    return _run_inner(start_dt, write_start_dt, end_date, batch_size, "全量计算")


def run_from_date(start_date: str, batch_size: int = 200) -> dict:
    """自定义起始日（等价于 run_full(start_date=...)）。"""
    return run_full(start_date=start_date, batch_size=batch_size)


def run_incremental(start_date=None,
                    batch_size: int = 200) -> dict:
    """双路径增量。

    - 跳空命中股票（stock_qfq_mark 中存在）：先删除其 stock_daily_calc_update
      历史数据 → 再按 stock_daily_analysis 全量数据从最早交易日重算到最新；
    - 未命中股票：保持原逻辑，只计算最新交易日一天。
    """
    print("=" * 72)
    print("本地滚动高低点计算脚本（增量/每日模式）启动")
    latest = _get_latest_trading_day()
    if latest is None:
        print("stock_daily_analysis 无数据，直接退出。")
        return {"rows_read": 0, "rows_written": 0, "stocks": 0}

    end_date_str = latest.strftime("%Y-%m-%d")
    print(f"  数据源   : stock_daily_analysis")
    print(f"  目标表   : stock_daily_calc_update")
    print(f"  最新交易日 : {end_date_str}")
    print("=" * 72)

    # ----------------------------------------------------
    # 第一步：读取本轮跳空命中股票（整表存在即视为"命中"）
    # ----------------------------------------------------
    hit_codes = _get_qfq_hit_stocks()
    total_hit = len(hit_codes)
    print(f"[1/2] 跳空命中股票数 : {total_hit}")

    hit_stats = {"rows_read": 0, "rows_written": 0, "stocks": 0}
    if total_hit > 0:
        # 先删除这些股票的历史计算数据
        print(f"  -> 删除 stock_daily_calc_update 中命中股票的历史数据 ...")
        deleted = _delete_stocks_from_calc(list(hit_codes))
        print(f"    已删除 {deleted} 行")

        # 只用"这批跳空股自己的最早交易日"作为起算点，避免用整表 MIN(date) 拉得过早
        earliest = _get_earliest_for_codes(list(hit_codes))
        if earliest is None:
            earliest = latest
        hit_start_dt = pd.Timestamp(earliest)
        print(f"  -> 全量重算（{earliest.strftime('%Y-%m-%d')} ~ {end_date_str}）")
        hit_stats = _run_inner(
            hit_start_dt, hit_start_dt, end_date_str, batch_size,
            "跳空命中-全量重算", only_codes=list(hit_codes),
        )

    # ----------------------------------------------------
    # 第二步：其余股票走增量（最新交易日一天）
    # ----------------------------------------------------
    print("[2/2] 未命中股票走增量模式（仅最新交易日一天）")
    latest_dt = pd.Timestamp(latest)
    inc_stats = _run_inner(
        latest_dt, latest_dt, end_date_str, batch_size,
        "未命中-增量计算", only_codes=None, exclude_codes=list(hit_codes),
    )

    # 汇总
    total_stocks = hit_stats.get("stocks", 0) + inc_stats.get("stocks", 0)
    total_rows = hit_stats.get("rows_written", 0) + inc_stats.get("rows_written", 0)
    # 整体区间：命中股的 start_date 到最新交易日
    overall_start = hit_stats.get("start_date", "") or inc_stats.get("start_date", "")

    print("")
    print("=" * 72)
    print("本次运行汇总：")
    print(f"  跳空命中  : {hit_stats.get('stocks', 0)} 只股票, "
          f"写入 {hit_stats.get('rows_written', 0)} 行")
    print(f"  增量更新  : {inc_stats.get('stocks', 0)} 只股票, "
          f"写入 {inc_stats.get('rows_written', 0)} 行")
    print("=" * 72)

    return {
        # 兼容 main.py 页面直接读取
        "rows_read": hit_stats.get("rows_read", 0) + inc_stats.get("rows_read", 0),
        "rows_written": total_rows,
        "stocks": total_stocks,
        "start_date": overall_start,
        "end_date": end_date_str,
        "elapsed_sec": hit_stats.get("elapsed_sec", 0) + inc_stats.get("elapsed_sec", 0),
        # 明细
        "hit": hit_stats,
        "incremental": inc_stats,
    }


if __name__ == "__main__":
    # 默认只跑"最新交易日一天"的增量。
    # 需要全量或自定义起始日时：
    stats = run_full(start_date="2024-06-01")
    #   stats = run_from_date(start_date="2023-06-01")
    #   stats = run_incremental(start_date="2024-06-01")
    # stats = run_incremental()
    print("完成，统计信息:", stats)
