"""一次性脚本：从东方财富 kline 接口拉取前复权日线，写入 stock_daily_analysis

用法示例：
    # 拉取 300854（中兰环保，创业板 → 市场号=0）最近 420 根 K 线并写入
    python fetch_kline_to_analysis.py --stock-code 300854 --market 0 --lmt 420
    # 或直接
    python fetch_kline_to_analysis.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import create_engine, text

_HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
_BACKEND = __import__("os").path.dirname(__import__("os").path.dirname(_HERE))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:
    from src.utils.config import settings  # type: ignore
except Exception:
    settings = None


# ---------------------------------------------------------------------------
# 常量 & 数据库连接
# ---------------------------------------------------------------------------
API_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    "?secid={market}.{code}"
    "&ut=fa5fd1943c7b386f172d6893dbfba10b"
    "&fields1=f1,f2,f3,f4,f5,f6"
    "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    "&klt=101"         # 101 = 日线
    "&fqt=1"           # 1 = 前复权
    "&end={end}"       # 截止日期 yyyyMMdd
    "&lmt={lmt}"       # 拉取条数，最大 420
    "&cb=quote_jp1"    # JSONP callback
)

# ---------------------------------------------------------------------------
# 爬虫策略 & HTTP 请求
# ---------------------------------------------------------------------------
# UA 池：每个股票随机抽一个；Referer 随机（增加指纹离散度）
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

_REFERERS = [
    "https://quote.eastmoney.com/",
    "https://quote.eastmoney.com/center/gridlist.html",
    "https://data.eastmoney.com/",
    "https://data.eastmoney.com/bkzj/",
]


def _build_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": random.choice(_REFERERS),
        "Connection": "keep-alive",
    }


def _fetch_with_retry(url: str,
                      max_retries: int = 3,
                      timeout: int = 15,
                      base_backoff: float = 1.0) -> requests.Response:
    """带随机抖动 + 指数退避的重试请求。

    - 每只股票使用新的随机 UA / Referer；
    - 首次失败：sleep(base_backoff * (1..2)) 后重试；
    - 第 n 次重试：sleep(base_backoff * 2^(n-1) * (1..2))；
    - 最后一次仍失败则抛出异常。
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            headers = _build_headers()
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries:
                break
            # 指数退避 + 随机抖动
            backoff = base_backoff * (2 ** (attempt - 1)) * random.uniform(1.0, 2.0)
            print(f"  [WARN] 第 {attempt} 次请求失败: {exc}；"
                  f"{backoff:.2f}s 后重试")
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc

TARGET_TABLE = "stock_daily_analysis"


def _build_engine():
    if settings is not None:
        user = settings.DB_USER
        password = settings.DB_PASSWORD
        host = settings.DB_HOST
        port = getattr(settings, "DB_PORT", 3306)
        database = settings.DB_NAME
    else:
        raise RuntimeError("未能加载 settings 配置，请确认 backend 目录在 PYTHONPATH")
    url = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        f"?charset=utf8mb4"
    )
    return create_engine(url)


engine = _build_engine()


# ---------------------------------------------------------------------------
# 建表
# ---------------------------------------------------------------------------
def ensure_target_table() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
      id INT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
      stock_code TEXT COMMENT '股票代码',
      stock_name TEXT COMMENT '股票名称',
      date DATE DEFAULT NULL COMMENT '交易日期',
      open DOUBLE DEFAULT NULL COMMENT '开盘价',
      close DOUBLE DEFAULT NULL COMMENT '收盘价',
      high DOUBLE DEFAULT NULL COMMENT '最高价',
      low DOUBLE DEFAULT NULL COMMENT '最低价',
      volume DOUBLE DEFAULT NULL COMMENT '成交量',
      amount DOUBLE DEFAULT NULL COMMENT '成交额',
      amplitude DOUBLE DEFAULT NULL COMMENT '振幅',
      change_rate DOUBLE DEFAULT NULL COMMENT '涨跌幅',
      change_amount DOUBLE DEFAULT NULL COMMENT '涨跌额',
      turnover DOUBLE DEFAULT NULL COMMENT '换手率',
      PRIMARY KEY (id),
      KEY idx_stock_code_date (stock_code(10), date),
      KEY idx_date (date),
      KEY idx_stock_code (stock_code(10))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
      COMMENT='股票前复权日线行情表（分析用）';
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


# ---------------------------------------------------------------------------
# 接口请求 & 解析
# ---------------------------------------------------------------------------
_JSONP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\((.*)\);?\s*$", re.DOTALL)


def _parse_jsonp(raw: str) -> Dict[str, Any]:
    m = _JSONP_RE.match(raw.strip())
    if not m:
        raise ValueError("响应不是合法 JSONP 格式")
    return json.loads(m.group(1))


def fetch_kline(
    stock_code: str,
    market: int,
    end_date: Optional[str] = None,
    lmt: int = 500,
    timeout: int = 15,
) -> Dict[str, Any]:
    """请求东方财富 kline/get 接口（带重试 + 随机 UA），返回解析后的 JSON dict。

    market: 0 = 深市/创业板/北交（常见 300xxx、00xxxx、8xxxx）；
            1 = 沪市（60xxxx、688xxx）。
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    url = API_URL.format(market=market, code=stock_code, end=end_date, lmt=lmt)
    resp = _fetch_with_retry(url, timeout=timeout)
    payload = _parse_jsonp(resp.text)
    if payload.get("rc") != 0:
        raise RuntimeError(f"接口返回非成功 rc={payload.get('rc')}, raw={payload}")
    return payload


# ---------------------------------------------------------------------------
# 字段映射
# ---------------------------------------------------------------------------
def klines_to_rows(payload: Dict[str, Any], stock_code: str) -> List[Dict[str, Any]]:
    """把 API 的 klines 列表转换为可直接写入表的 dict 行。

    klines 每项："date, open, close, high, low, volume, amount,
                   amplitude, change_rate, change_amount, turnover"
    """
    data = payload.get("data") or {}
    klines: List[str] = data.get("klines") or []
    stock_name: str = data.get("name", "")

    rows: List[Dict[str, Any]] = []
    for raw in klines:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 11:
            # 字段缺失，跳过
            continue
        try:
            date_str = parts[0]                   # 2026-05-18
            open_v = float(parts[1])
            close_v = float(parts[2])
            high_v = float(parts[3])
            low_v = float(parts[4])
            volume_v = float(parts[5])
            amount_v = float(parts[6])
            amplitude_v = float(parts[7])
            change_rate_v = float(parts[8])
            change_amount_v = float(parts[9])
            turnover_v = float(parts[10])
        except (TypeError, ValueError):
            continue

        rows.append({
            "stock_code": stock_code,
            "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
            "open": open_v,
            "close": close_v,
            "high": high_v,
            "low": low_v,
            "volume": volume_v,
            "amount": amount_v,
            "amplitude": amplitude_v,
            "change_rate": change_rate_v,
            "change_amount": change_amount_v,
            "turnover": turnover_v,
            "stock_name": stock_name,
        })
    return rows


# ---------------------------------------------------------------------------
# 写入：清空该股全部历史，再插入本批次全部数据
# ---------------------------------------------------------------------------
def replace_all_rows(stock_code: str, rows: List[Dict[str, Any]]) -> int:
    """对单只股票：先删除 stock_daily_analysis 中的全部历史记录，再插入本批次。

    用“全量覆盖”的方式，保证除权除息等场景下表内数据与最新前复权口径一致。
    """
    if not rows:
        return 0

    with engine.begin() as conn:
        # 1) 清空该股全部历史（按 stock_code 删除即可）
        del_sql = text(
            f"DELETE FROM {TARGET_TABLE} WHERE stock_code = :code"
        )
        conn.execute(del_sql, {"code": stock_code})

        # 2) 批量插入本批次爬取的全部数据
        ins_sql = text(
            f"INSERT INTO {TARGET_TABLE} "
            f"(stock_code, date, open, close, high, low, volume, amount, "
            f" amplitude, change_rate, change_amount, turnover, stock_name) "
            f"VALUES (:stock_code, :date, :open, :close, :high, :low, "
            f"        :volume, :amount, :amplitude, :change_rate, "
            f"        :change_amount, :turnover, :stock_name)"
        )
        conn.execute(ins_sql, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# 标记表更新：完成单股后，把 last_refresh_qfq 置 NOW，need_refresh 置 1
# ---------------------------------------------------------------------------
def mark_refresh_done(stock_code: str) -> None:
    """完成单股前复权数据覆盖后，同步更新 stock_qfq_mark.last_refresh_qfq。"""
    sql = text(
        "UPDATE stock_qfq_mark SET last_refresh_qfq = NOW() WHERE stock_code = :code"
    )
    with engine.begin() as conn:
        conn.execute(sql, {"code": stock_code})


# ---------------------------------------------------------------------------
# 从标记表获取需要刷新前复权数据的股票
# ---------------------------------------------------------------------------
def fetch_mark_codes() -> list:
    """从 stock_qfq_mark 读取本轮被标记为"跳空/除权命中"的全部股票代码。

    表中存在的即表示本轮需要全量刷新前复权数据；不存在的为"未命中"，
    走后续增量/不动路径。
    """
    try:
        sql = text(
            "SELECT stock_code FROM stock_qfq_mark ORDER BY last_refresh_qfq DESC"
        )
        with engine.begin() as conn:
            rows = conn.execute(sql).mappings().all()
    except Exception:
        # 表尚未创建或临时不可用 → 视为"当前无需要刷新的股票"
        return []
    return [r["stock_code"] for r in rows]


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def detect_market(stock_code: str) -> int:
    """根据股票代码粗略推断 market 号。

    规则：60 / 688 / 900 → 沪市 market=1；其它（00 / 30 / 15 / 8 / 43）→ 深市/北交 market=0。
    外部可显式传入 --market 覆盖此推断。
    """
    code = stock_code.strip()
    if code.startswith(("60", "68", "900")):
        return 1
    return 0


def refresh_one_stock(stock_code: str, market: Optional[int], lmt: int,
                      end_date: Optional[str] = None,
                      min_sleep: float = 0.3,
                      max_sleep: float = 1.0) -> dict:
    """拉取 + 覆盖写入 + 标记完成，单股流程。返回统计 dict；失败返回含 error 字段。

    爬虫策略：完成本只股票后，在 [min_sleep, max_sleep] 区间随机休眠，
    防止固定频率触发反爬。
    """
    t0 = time.time()
    print(f"  [{datetime.now():%H:%M:%S}] -> {stock_code}", end="", flush=True)

    if market is None:
        market = detect_market(stock_code)

    try:
        payload = fetch_kline(stock_code=stock_code, market=market,
                              end_date=end_date, lmt=lmt)
    except Exception as exc:
        print(f"  接口异常: {exc}")
        return {"stock_code": stock_code, "rows_written": 0, "error": str(exc)}

    rows = klines_to_rows(payload, stock_code)
    if not rows:
        print("  空数据，跳过")
        return {"stock_code": stock_code, "rows_written": 0, "error": "empty klines"}

    try:
        rows_written = replace_all_rows(stock_code, rows)
        mark_refresh_done(stock_code)
    except Exception as exc:
        print(f"  写入异常: {exc}")
        return {"stock_code": stock_code, "rows_written": 0, "error": str(exc)}

    print(f"  {rows[0]['date']}~{rows[-1]['date']} 共 {len(rows)} 行 "
          f"({time.time() - t0:.2f}s)")

    # 随机降频，避免固定间隔被识别为爬虫
    if max_sleep > 0 and max_sleep >= min_sleep:
        sleep_s = random.uniform(min_sleep, max_sleep)
        time.sleep(sleep_s)

    return {
        "stock_code": stock_code,
        "stock_name": rows[0]["stock_name"],
        "rows_written": rows_written,
        "first_date": rows[0]["date"].strftime("%Y-%m-%d"),
        "last_date": rows[-1]["date"].strftime("%Y-%m-%d"),
        "elapsed_sec": time.time() - t0,
    }


def run_loop(market, lmt: int,
             end_date: Optional[str] = None,
             min_sleep: float = 0.3,
             max_sleep: float = 1.0) -> dict:
    """从 stock_qfq_mark 读取本轮被标记为跳空的股票，乱序后逐个覆盖更新。

    - 读取：stock_daily_analysis（表结构一致），按 (stock_code, date) DELETE 旧记录，
      再插入本轮全部解析结果；
    - 回写：stock_qfq_mark.last_refresh_qfq 为 NOW()（标记"已完成前复权覆盖"。
    """
    t0 = time.time()
    print("=" * 72)
    print(f"[{datetime.now():%H:%M:%S}] stock_daily_analysis 前复权覆盖更新")
    print(f"  数据源       : stock_qfq_mark（本轮所有命中）")
    print(f"  每只后随机休眠 : {min_sleep:.2f}~{max_sleep:.2f}s")
    print("=" * 72)

    ensure_target_table()

    codes = fetch_mark_codes()
    total = len(codes)
    if total == 0:
        print("  没有需要刷新的股票。")
        return {"total": 0, "succeeded": 0, "failed": 0, "elapsed_sec": time.time() - t0}

    # 乱序处理，减少对接口的固定访问模式
    random.shuffle(codes)
    print(f"  共 {total} 只股票待刷新")

    results = []
    for code in codes:
        r = refresh_one_stock(code, market, lmt, end_date,
                           min_sleep=min_sleep, max_sleep=max_sleep)
        results.append(r)

    succeeded = sum(1 for r in results if "error" not in r)
    failed = total - succeeded

    print("")
    print(f"[{datetime.now():%H:%M:%S}] 完成: 成功 {succeeded}/{total}，失败 {failed}，总耗时 {time.time() - t0:.2f}s")
    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_sec": time.time() - t0,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="从东方财富拉取前复权日线并写入 stock_daily_analysis"
    )
    p.add_argument("--market", type=int, default=None,
                   help="市场号：0=深/北交/创业板，1=沪市。默认自动推断。")
    p.add_argument("--lmt", type=int, default=500,
                   help="单只股票拉取 K 线数量（东方财富最多 500，约 2 年）")
    p.add_argument("--end", default=None, help="截止日期 yyyyMMdd，默认今日")
    p.add_argument("--min-sleep", type=float, default=0.3,
                   help="每只股票后随机休眠下界（秒），默认 0.3")
    p.add_argument("--max-sleep", type=float, default=1.0,
                   help="每只股票后随机休眠上界（秒），默认 1.0。设 0 则不休眠")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    stats = run_loop(
        market=args.market,
        lmt=args.lmt,
        end_date=args.end,
        min_sleep=args.min_sleep,
        max_sleep=args.max_sleep,
    )
    print("完成，统计信息:", stats)
