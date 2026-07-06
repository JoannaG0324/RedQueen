"""
行业指数滚动高低点计算脚本（对应个股版 calc_hl_mid.py 的行业版）
=================================================================

数据源: industry_ths_index
目标表: industry_ths_index_calc_update

计算规则（与个股版保持一致）：
  1. 按 industry_code 分组独立处理，日线按 date 升序排序
  2. 每行预计算 hl_mid = (high + low) / 2
  3. 滚动窗口：20 / 60 / 90 / 120 个交易日（按K线条数统计）
  4. 周期高点：窗口内 hl_mid 最大值首次出现那一行的 high 与 date
     周期低点：窗口内 hl_mid 最小值首次出现那一行的 low  与 date
  5. 边界:
       ① 行业累计K线数 < 对应窗口长度 → 该周期字段全部 NULL
       ② 当日 high 或 low 为空 → 该行所有周期指标置 NULL
       ③ 同一窗口多个交易日同为极值 → 保留最早出现的那一个
  6. 写入: 对 (industry_code, date) 唯一键使用
     INSERT ... ON DUPLICATE KEY UPDATE，不 DELETE，不新增重复行。

对外函数（参数命名保持一致）：
  run_full(start_date="2024-06-01", batch_size=50)
      全量：从 start_date 到 industry_ths_index 最新交易日，重算。

  run_from_date(start_date, batch_size=50)
      自定义起始日：等价于 run_full(start_date=...)。

  run_incremental(start_date=None, batch_size=50)
      增量：
        ① 若传了 start_date → 从 start_date 到最新交易日；
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
_HISTORY_MARGIN_DAYS = 365


def _calc_one_industry(df_industry: pd.DataFrame) -> pd.DataFrame:
    """单行业滚动高低点计算（向量化实现，见 calc_hl_mid.py 注释）。"""
    df = df_industry.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", kind="mergesort").reset_index(drop=True)

    df["hl_mid"] = (df["high"].astype(float) + df["low"].astype(float)) / 2.0

    suspend_mask = df["high"].isna() | df["low"].isna()

    hl_mid_arr = np.asarray(df["hl_mid"], dtype=float)
    high_arr = np.asarray(df["high"], dtype=float)
    low_arr = np.asarray(df["low"], dtype=float)
    date_arr = np.asarray(df["date"])
    n = len(df)

    from numpy.lib.stride_tricks import sliding_window_view  # numpy >= 1.20

    for window in WINDOWS:
        high_col = f"high_{window}d"
        high_date_col = f"high_{window}d_date"
        low_col = f"low_{window}d"
        low_date_col = f"low_{window}d_date"

        df[high_col] = np.nan
        df[high_date_col] = pd.NaT
        df[low_col] = np.nan
        df[low_date_col] = pd.NaT

        if n < window:
            continue

        roll = sliding_window_view(hl_mid_arr, window)
        nan_mask = np.isnan(roll)

        with np.errstate(invalid="ignore", all="ignore"):
            maxval = np.nanmax(roll, axis=1)
            minval = np.nanmin(roll, axis=1)

        first_max = (roll == maxval[:, None]).argmax(axis=1)
        first_min = (roll == minval[:, None]).argmin(axis=1)

        rows = np.arange(window - 1, n)
        abs_idx_max = rows - (window - 1) + first_max
        abs_idx_min = rows - (window - 1) + first_min

        high_vals = high_arr[abs_idx_max]
        low_vals = low_arr[abs_idx_min]
        high_dates = date_arr[abs_idx_max]
        low_dates = date_arr[abs_idx_min]

        all_nan = nan_mask.all(axis=1)
        high_vals[all_nan] = np.nan
        low_vals[all_nan] = np.nan

        df.loc[rows, high_col] = high_vals
        df.loc[rows, low_col] = low_vals
        df.loc[rows, high_date_col] = high_dates
        df.loc[rows, low_date_col] = low_dates

    calc_cols = []
    for w in WINDOWS:
        calc_cols += [
            f"high_{w}d", f"high_{w}d_date",
            f"low_{w}d",  f"low_{w}d_date",
        ]
    df.loc[suspend_mask, calc_cols] = np.nan

    df["high_20d_last"] = np.nan
    if "high_20d" in df.columns:
        valid_mask = ~df["high_20d"].isna()
        if valid_mask.any():
            diff = df["high_20d"].ne(df["high_20d"].shift(1))
            group_id = diff.cumsum()
            df.loc[valid_mask, "high_20d_last"] = df[valid_mask].groupby(group_id[valid_mask]).cumcount() + 1

    return df


# ---------------------------------------------------------------------------
# 建表 & 写入
# ---------------------------------------------------------------------------
def ensure_target_table() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS industry_ths_index_calc_update (
      id BIGINT NOT NULL AUTO_INCREMENT COMMENT '自增主键',
      industry_code VARCHAR(20) NOT NULL COMMENT 'THS行业代码',
      date DATE NOT NULL COMMENT '计算对应的交易日',

      high_20d  DOUBLE DEFAULT NULL,
      high_20d_date  DATE DEFAULT NULL,
      low_20d   DOUBLE DEFAULT NULL,
      low_20d_date   DATE DEFAULT NULL,
      high_20d_last INT DEFAULT NULL COMMENT '20D均价高点连续保持天数',

      high_60d  DOUBLE DEFAULT NULL,
      high_60d_date  DATE DEFAULT NULL,
      low_60d   DOUBLE DEFAULT NULL,
      low_60d_date   DATE DEFAULT NULL,

      high_90d  DOUBLE DEFAULT NULL,
      high_90d_date  DATE DEFAULT NULL,
      low_90d   DOUBLE DEFAULT NULL,
      low_90d_date   DATE DEFAULT NULL,

      high_120d DOUBLE DEFAULT NULL,
      high_120d_date DATE DEFAULT NULL,
      low_120d  DOUBLE DEFAULT NULL,
      low_120d_date  DATE DEFAULT NULL,

      calc_time DATETIME DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '指标计算更新时间',

      PRIMARY KEY (id),
      UNIQUE KEY uk_industry_date (industry_code, date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COMMENT '本地脚本-行业指数多周期滚动均价高低点计算结果表';
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
    if df_out is None or df_out.empty:
        return 0

    cols = [
        "industry_code", "date",
        "high_20d", "high_20d_date", "low_20d", "low_20d_date", "high_20d_last",
        "high_60d", "high_60d_date", "low_60d", "low_60d_date",
        "high_90d", "high_90d_date", "low_90d", "low_90d_date",
        "high_120d", "high_120d_date", "low_120d", "low_120d_date",
    ]
    rows = []
    for _, r in df_out.iterrows():
        row: dict = {
            "industry_code": r["industry_code"],
            "date": _format_date(r["date"]),
            "high_20d_last": (
                None if pd.isna(r.get("high_20d_last")) else int(r["high_20d_last"])
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
        [f"{c}=VALUES({c})" for c in cols if c not in ("industry_code", "date")]
    )
    sql = (
        f"INSERT INTO industry_ths_index_calc_update ({col_list}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return len(rows)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _get_latest_trading_day() -> Optional[datetime]:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT MAX(date) FROM industry_ths_index")
            ).scalar()
        if row is None:
            return None
        return pd.to_datetime(row).to_pydatetime()
    except Exception:
        return None


def _load_industry_data(read_start: str, read_end: str) -> pd.DataFrame:
    sql = (
        "SELECT industry_code, date, high, low FROM industry_ths_index "
        "WHERE date BETWEEN :start AND :end "
        "ORDER BY industry_code, date"
    )
    df = pd.read_sql(text(sql), engine, params={"start": read_start, "end": read_end})
    return df


def _run_inner(start_dt: pd.Timestamp,
               write_start_dt: pd.Timestamp,
               end_date: str,
               batch_size: int,
               mode_label: str) -> dict:
    """统一的『读取 → 分组计算 → 分批 upsert』主循环。"""
    read_start_dt = start_dt - pd.Timedelta(days=_HISTORY_MARGIN_DAYS)
    read_start = read_start_dt.strftime("%Y-%m-%d")

    ensure_target_table()

    t0 = time.time()
    print(f"[{datetime.now():%H:%M:%S}] 读取源表 industry_ths_index "
          f"({read_start} ~ {end_date}) ...")
    df_all = _load_industry_data(read_start, end_date)
    print(f"    读取 {len(df_all)} 行，用时 {time.time() - t0:.2f}s")

    if df_all.empty:
        print("源表区间内无数据，结束。")
        return {"rows_read": 0, "rows_written": 0, "industries": 0}

    df_all["date"] = pd.to_datetime(df_all["date"])

    total_industries = df_all["industry_code"].nunique()
    total_written = 0
    processed = 0

    buffer: list = []
    t_calc = time.time()

    for industry_code, grp in df_all.groupby("industry_code", sort=True):
        try:
            df_calc = _calc_one_industry(grp)
            df_calc["industry_code"] = industry_code
            df_out = df_calc[df_calc["date"] >= write_start_dt].copy()
            if not df_out.empty:
                buffer.append(df_out)
        except Exception as exc:
            print(f"  [WARN] 行业 {industry_code} 计算失败: {exc}")
            continue

        processed += 1
        if len(buffer) >= batch_size:
            out = pd.concat(buffer, ignore_index=True)
            total_written += upsert_calc_rows(out)
            buffer = []
            print(f"\r[{datetime.now():%H:%M:%S}] 进度 {processed}/{total_industries} "
                  f"已写入 {total_written} 行", end="", flush=True)

    if buffer:
        out = pd.concat(buffer, ignore_index=True)
        total_written += upsert_calc_rows(out)
        buffer = []

    print("")
    print(f"[{datetime.now():%H:%M:%S}] {mode_label}完成，用时 {time.time() - t_calc:.2f}s")
    print(f"  行业数 : {total_industries}")
    print(f"  写入行 : {total_written}")

    return {
        "rows_read": len(df_all),
        "rows_written": total_written,
        "industries": total_industries,
        "elapsed_sec": time.time() - t0,
        "start_date": write_start_dt.strftime("%Y-%m-%d"),
        "end_date": end_date,
        "mode": mode_label,
    }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def run_full(start_date: str = "2024-06-01", batch_size: int = 50) -> dict:
    """全量：从 start_date 到最新交易日，每个行业重算区间内每一天的滚动高低点。"""
    print("=" * 72)
    print("行业指数滚动高低点计算脚本（全量模式）启动")
    latest = _get_latest_trading_day()
    if latest is None:
        print("industry_ths_index 无数据，直接退出。")
        return {"rows_read": 0, "rows_written": 0, "industries": 0}

    end_date = latest.strftime("%Y-%m-%d")
    start_dt = pd.to_datetime(start_date)
    write_start_dt = start_dt

    print(f"  数据源   : industry_ths_index")
    print(f"  目标表   : industry_ths_index_calc_update")
    print(f"  日期区间 : {start_date} ~ {end_date}")
    print(f"  滚动窗口 : {WINDOWS}")
    print("=" * 72)

    return _run_inner(start_dt, write_start_dt, end_date, batch_size, "全量计算")


def run_from_date(start_date: str, batch_size: int = 50) -> dict:
    """自定义起始日（等价于 run_full(start_date=...)）。"""
    return run_full(start_date=start_date, batch_size=batch_size)


def run_incremental(start_date: Optional[str] = None,
                    batch_size: int = 50) -> dict:
    """增量。

    - 传了 start_date → 从 start_date 到最新交易日；
    - 否则 → 仅"最新交易日"一天。
    """
    print("=" * 72)
    print("行业指数滚动高低点计算脚本（增量/每日模式）启动")
    latest = _get_latest_trading_day()
    if latest is None:
        print("industry_ths_index 无数据，直接退出。")
        return {"rows_read": 0, "rows_written": 0, "industries": 0}

    end_date = latest.strftime("%Y-%m-%d")
    if start_date:
        write_start_dt = pd.to_datetime(start_date)
        print(f"  写入区间 : {start_date} ~ {end_date}（由 start_date 指定）")
    else:
        write_start_dt = pd.Timestamp(latest)
        print(f"  写入日期 : {end_date}（仅最新交易日一天）")

    print(f"  数据源   : industry_ths_index")
    print(f"  目标表   : industry_ths_index_calc_update")
    print(f"  滚动窗口 : {WINDOWS}")
    print("=" * 72)

    return _run_inner(write_start_dt, write_start_dt, end_date, batch_size, "增量计算")


if __name__ == "__main__":
    # 默认只跑"最新交易日一天"的增量。
    # 需要全量或自定义起始日时：
    # stats = run_full(start_date="2024-06-01")
    #   stats = run_from_date(start_date="2023-06-01")
    stats = run_incremental()
    print("完成，统计信息:", stats)
