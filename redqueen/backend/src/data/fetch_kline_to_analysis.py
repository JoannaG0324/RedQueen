"""从前复权日线接口拉取数据，覆盖写入 stock_daily_analysis

支持两个独立数据源，通过前端弹窗选择（默认东财）：
  - eastmoney: 东方财富 kline 接口
  - xueqiu: 雪球 kline.json 接口（需登录 cookies，配置在 config/cookies.py）

核心特性：
  - 单个股票拉取失败立即终止任务，不再继续遍历
  - 雪球数据源振幅计算：(当日 high - 当日 low) / 前一日 close * 100%
  - 雪球数据源 volume 单位转换：股 → 手（除以 100 取整）

用法示例：
    # 拉取 300854（中兰环保，创业板 → 市场号=0）最近 420 根 K 线并写入
    python fetch_kline_to_analysis.py --stock-code 300854 --market 0 --lmt 420
    # 指定数据源为雪球
    python fetch_kline_to_analysis.py --stock-code 300854 --data-source xueqiu
    # 或直接运行（从 stock_qfq_mark 读取标记股票）
    python fetch_kline_to_analysis.py

源表：stock_qfq_mark, stock_daily_analysis
目标表：stock_daily_analysis
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


def fetch_kline_from_eastmoney(
    stock_code: str,
    market: Optional[int] = None,
    end_date: Optional[str] = None,
    lmt: int = 500,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """独立功能：从东方财富请求个股前复权日线数据。

    输入参数：
        stock_code: 股票代码，例如 "300854" / "600519"
        market    : 市场号；None 时根据 stock_code 自动推断
                    0 = 深市/创业板/北交（300xxx、00xxxx、8xxxx）
                    1 = 沪市（60xxxx、688xxx）
        end_date  : 截止日期 yyyyMMdd，None 则用今天
        lmt       : 拉取条数，东财最大 420~500
        timeout   : HTTP 单次请求超时（秒）

    返回：统一行结构 dict 列表，每行字段同 klines_to_rows 输出：
        stock_code, date, open, close, high, low, volume(手), amount,
        amplitude, change_rate, change_amount, turnover, stock_name
    """
    if market is None:
        market = detect_market(stock_code)
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    url = API_URL.format(market=market, code=stock_code, end=end_date, lmt=lmt)
    resp = _fetch_with_retry(url, timeout=timeout)
    payload = _parse_jsonp(resp.text)
    if payload.get("rc") != 0:
        raise RuntimeError(f"东财接口返回非成功 rc={payload.get('rc')}, raw={payload}")
    return klines_to_rows(payload, stock_code)


# ---------------------------------------------------------------------------
# 雪球备用数据源 
# ---------------------------------------------------------------------------

XUEQIU_BASE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"

from config.cookies import XUEQIU_LOGIN_COOKIES

# column 顺序: ["timestamp","volume","open","high","low","close","chg","percent",
#              "turnoverrate","amount","volume_post","amount_post"]
_IDX_TIMESTAMP = 0
_IDX_VOLUME_SHARES = 1
_IDX_OPEN = 2
_IDX_HIGH = 3
_IDX_LOW = 4
_IDX_CLOSE = 5
_IDX_CHG = 6
_IDX_PERCENT = 7
_IDX_TURNOVER = 8
_IDX_AMOUNT = 9


def _xueqiu_prefix_for_code(code: str) -> str:
    """按代码首字推断市场前缀：6→SH / 0 或 3→SZ / 9→BJ。"""
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith("9"):
        return "BJ"
    return "SZ"


def _build_xueqiu_symbol(stock_code: str, market: Optional[int] = None) -> str:
    """把裸股票代码转换为雪球 symbol：6→SH、0/3→SZ、9→BJ。"""
    if market is not None:
        # 保持与 detect_market 返回值兼容：0→SZ、1→SH、2→BJ
        mapping = {0: "SZ", 1: "SH", 2: "BJ"}
        prefix = mapping.get(market, _xueqiu_prefix_for_code(stock_code))
    else:
        prefix = _xueqiu_prefix_for_code(stock_code)
    return f"{prefix}{stock_code}"


def _xueqiu_rows_from_payload(payload: Dict[str, Any],
                              stock_code: str) -> List[Dict[str, Any]]:
    """把雪球 kline.json 返回的 payload 解析为统一行结构。"""
    if payload.get("error_code") != 0:
        raise RuntimeError(
            f"雪球接口返回非成功 error_code={payload.get('error_code')}, "
            f"error_description={payload.get('error_description')}"
        )

    data = payload.get("data") or {}
    symbol = data.get("symbol", "")
    items: List[List[Any]] = data.get("item") or []

    rows: List[Dict[str, Any]] = []
    for item in items:
        if not item or len(item) < 10:
            continue
        try:
            ts_ms = int(item[_IDX_TIMESTAMP])
            dt = datetime.fromtimestamp(ts_ms / 1000)
            date_v = dt.date()

            open_v = float(item[_IDX_OPEN])
            high_v = float(item[_IDX_HIGH])
            low_v = float(item[_IDX_LOW])
            close_v = float(item[_IDX_CLOSE])

            # 雪球 volume 单位是"股"，本系统以"手"存储；1 手 = 100 股，取整
            volume_shares = float(item[_IDX_VOLUME_SHARES])
            volume_hands = int(volume_shares / 100)

            amount_v = float(item[_IDX_AMOUNT])

            # 部分字段雪球与东财命名/口径略有差异，做近似映射
            chg_v = float(item[_IDX_CHG]) if item[_IDX_CHG] is not None else 0.0
            percent_v = (
                float(item[_IDX_PERCENT]) if item[_IDX_PERCENT] is not None else 0.0
            )
            turnover_v = (
                float(item[_IDX_TURNOVER]) if item[_IDX_TURNOVER] is not None else 0.0
            )
        except (TypeError, ValueError):
            continue

        rows.append({
            "stock_code": stock_code,
            "date": date_v,
            "open": open_v,
            "close": close_v,
            "high": high_v,
            "low": low_v,
            "volume": float(volume_hands),
            "amount": amount_v,
            "amplitude": 0.0,
            "change_rate": percent_v,
            "change_amount": chg_v,
            "turnover": turnover_v,
            # 雪球响应仅返回 symbol 代码，无股票名称，
            # 由上层 _fill_xueqiu_stock_name 从 stock_qfq_scan /
            # stock_daily_analysis / stock_info 查询回填。
            "stock_name": symbol,
            "_data_source": "xueqiu",
        })

    for i in range(len(rows)):
        row = rows[i]
        high_v = row["high"]
        low_v = row["low"]
        prev_close = rows[i - 1]["close"] if i > 0 else row["close"]
        if prev_close:
            row["amplitude"] = (high_v - low_v) / prev_close * 100.0
        else:
            row["amplitude"] = 0.0

    return rows


def _fill_xueqiu_stock_name(stock_code: str,
                            rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对切换到雪球数据源后的行情记录，回填 stock_name。

    只从 stock_daily_analysis 表查询：按 date 倒序取该 stock_code
    最新一条非空 stock_name；查不到则保留原值并打印 warning。
    """
    if not rows:
        return rows

    candidate: Optional[str] = None

    try:
        with engine.begin() as conn:
            r = conn.execute(
                text(
                    "SELECT stock_name FROM stock_daily_analysis "
                    "WHERE stock_code = :code "
                    "AND stock_name IS NOT NULL "
                    "AND stock_name <> '' "
                    "ORDER BY date DESC LIMIT 1"
                ),
                {"code": stock_code},
            ).scalar()
            if r:
                candidate = str(r).strip()
    except Exception as exc:
        print(f"  [WARN] 查询 stock_name 失败（{stock_code}）: {exc}")

    if not candidate:
        print(f"  [WARN] stock_daily_analysis 未找到 {stock_code} 的 stock_name，保留原值")
        return rows

    for r in rows:
        r["stock_name"] = candidate
    return rows


def fetch_kline_from_xueqiu(
    stock_code: str,
    market: Optional[int] = None,
    bar_count: int = 500,
    end_date: Optional[str] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """独立功能：从雪球请求个股日线数据（备用数据源）。

    输入参数：
        stock_code: 股票代码，例如 "300854" / "600519"
        market    : 市场号；None 时根据 stock_code 自动推断
        bar_count : 拉取 K 线数量；count 传 -bar_count 表示"截止 begin 向前 N 根"
        end_date  : 截止日期 yyyyMMdd，None 则使用当前时间
        cookies   : 雪球登录态 cookies；None 时使用本文件内置常量
        timeout   : HTTP 单次请求超时（秒）
        max_retries: 失败重试次数

    返回：与 fetch_kline_from_eastmoney 相同的统一行结构 dict 列表。
    注意：volume 字段以"手"为单位（从雪球原始"股"除以 100 取整）。
    """
    if cookies is None:
        cookies = XUEQIU_LOGIN_COOKIES

    symbol = _build_xueqiu_symbol(stock_code, market)

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Referer": f"https://xueqiu.com/{symbol}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }

    session = requests.Session()
    for k, v in cookies.items():
        session.cookies.set(k, v)

    if end_date:
        # yyyyMMdd → 当日 00:00 毫秒时间戳（与东财 end 参数对齐）
        begin_ms = int(
            datetime.strptime(end_date, "%Y%m%d").timestamp() * 1000
        )
    else:
        begin_ms = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "period": "day",
        "type": "before",
        "begin": begin_ms,
        "count": -bar_count,
        "indicator": "kline",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(
                XUEQIU_BASE_URL,
                headers=headers,
                params=params,
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = _xueqiu_rows_from_payload(payload, stock_code)
            # 雪球响应不包含中文股票名称，从数据库回查 stock_name 回填
            rows = _fill_xueqiu_stock_name(stock_code, rows)
            # 去掉仅用于本文件内部跟踪的列
            for r in rows:
                r.pop("_data_source", None)
            return rows
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries:
                break
            backoff = 1.0 * (2 ** (attempt - 1)) * random.uniform(1.0, 2.0)
            print(f"  [WARN] 第 {attempt} 次雪球请求失败: {exc}；"
                  f"{backoff:.2f}s 后重试")
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc


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
# 标记表更新：完成单股后，把 last_refresh_qfq 置 NOW
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
            "SELECT stock_code FROM stock_qfq_mark WHERE last_refresh_qfq IS NULL"
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
    """根据股票代码推断 market 号。

    规则：
        以 6 开头（60 / 688 / 601…）→ 沪市 market = 1
        以 9 开头（900 / 920 / 900…）→ 北交所 market = 2
        其它（00 / 30 / 15 / 8 / 43…）→ 深市 / 创业板 market = 0
    外部可显式传入 --market 覆盖此推断。
    """
    code = stock_code.strip()
    if code.startswith("6"):
        return 1
    if code.startswith("9"):
        return 2
    return 0


def refresh_one_stock(stock_code: str, market: Optional[int], lmt: int,
                      end_date: Optional[str] = None,
                      min_sleep: float = 1.0,
                      max_sleep: float = 5.0,
                      data_source: str = "eastmoney") -> dict:
    """拉取 + 覆盖写入 + 标记完成，单股流程。返回统计 dict；失败抛出异常。

    data_source: "eastmoney" 或 "xueqiu"，按指定数据源拉取，不再自动回落。
    """
    t0 = time.time()
    print(f"  [{datetime.now():%H:%M:%S}] -> {stock_code}", end="", flush=True)

    if market is None:
        market = detect_market(stock_code)

    rows: List[Dict[str, Any]] = []
    error_msg: Optional[str] = None

    if data_source == "eastmoney":
        try:
            rows = fetch_kline_from_eastmoney(
                stock_code=stock_code, market=market,
                end_date=end_date, lmt=lmt,
            )
        except Exception as exc:
            error_msg = str(exc)
            rows = []
    elif data_source == "xueqiu":
        try:
            rows = fetch_kline_from_xueqiu(
                stock_code=stock_code, market=market,
                bar_count=lmt, end_date=end_date,
            )
        except Exception as exc:
            error_msg = str(exc)
            rows = []
    else:
        raise ValueError(f"未知数据源: {data_source}")

    if not rows:
        raise RuntimeError(
            f"[fetch_kline_to_analysis] {stock_code} 未获取到行情数据，"
            f"data_source={data_source}，"
            f"error={error_msg or 'empty klines'}；数据源异常，请检查网络或 cookies"
        )

    try:
        rows_written = replace_all_rows(stock_code, rows)
        mark_refresh_done(stock_code)
    except Exception as exc:
        raise RuntimeError(
            f"[fetch_kline_to_analysis] {stock_code} 写入数据库失败: {exc}"
        ) from exc

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
        "data_source": data_source,
    }


def run_loop(market, lmt: int,
             end_date: Optional[str] = None,
             min_sleep: float = 1.5,
             max_sleep: float = 5,
             data_source: str = "eastmoney",
             stock_code: Optional[str] = None) -> dict:
    """从 stock_qfq_mark 读取本轮被标记为跳空的股票，乱序后逐个覆盖更新。

    - 读取：stock_daily_analysis（表结构一致），按 (stock_code, date) DELETE 旧记录，
      再插入本轮全部解析结果；
    - 回写：stock_qfq_mark.last_refresh_qfq 为 NOW()（标记"已完成前复权覆盖"）；
    - 当传入 stock_code 时，仅刷新该只股票，用于调试；
    - data_source: "eastmoney" 或 "xueqiu"，按指定数据源拉取，不再自动回落。
    """
    t0 = time.time()
    print("=" * 72)
    print(f"[{datetime.now():%H:%M:%S}] stock_daily_analysis 前复权覆盖更新")
    print(f"  数据源       : {data_source}")
    print(f"  每只后随机休眠 : {min_sleep:.2f}~{max_sleep:.2f}s")
    print("=" * 72)

    ensure_target_table()

    if stock_code:
        codes = [stock_code]
    else:
        codes = fetch_mark_codes()
    total = len(codes)
    if total == 0:
        print("  没有需要刷新的股票。")
        return {"total": 0, "succeeded": 0, "failed": 0, "elapsed_sec": time.time() - t0}

    if not stock_code:
        random.shuffle(codes)
    print(f"  共 {total} 只股票待刷新")

    results = []
    for code in codes:
        r = refresh_one_stock(code, market, lmt, end_date,
                              min_sleep=min_sleep, max_sleep=max_sleep,
                              data_source=data_source)
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
        description="从前复权日线接口拉取数据并写入 stock_daily_analysis（支持 eastmoney/xueqiu）"
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
    p.add_argument("--stock-code", default=None,
                   help="可选：只刷新单只股票代码，用于调试；未传则遍历标记表")
    p.add_argument("--data-source", choices=["eastmoney", "xueqiu"], default="eastmoney",
                   help="数据源：eastmoney（东方财富）或 xueqiu（雪球），默认 eastmoney")
    p.add_argument("--dry-run-eastmoney", action="store_true",
                   help="仅从东财拉取并打印前 N 行，不写库（测试 fetch_kline_from_eastmoney）")
    p.add_argument("--dry-run-xueqiu", action="store_true",
                   help="仅从雪球拉取并打印前 N 行，不写库（测试 fetch_kline_from_xueqiu）")
    p.add_argument("--dry-limit", type=int, default=5,
                   help="dry-run 时打印前多少行，默认 5")
    return p.parse_args()


def _pprint_rows(rows: List[Dict[str, Any]], limit: int) -> None:
    print(f"共拉取 {len(rows)} 行；打印前 {limit} 行：")
    for r in rows[:limit]:
        print(
            f"  date={r['date']} open={r['open']} close={r['close']} "
            f"high={r['high']} low={r['low']} volume={r['volume']} "
            f"amount={r['amount']} change_rate={r['change_rate']}% change_amout={r['change_amount']}")


if __name__ == "__main__":
    args = parse_args()

    if args.dry_run_eastmoney and args.stock_code:
        rows = fetch_kline_from_eastmoney(
            stock_code=args.stock_code,
            market=args.market,
            end_date=args.end,
            lmt=args.lmt,
        )
        _pprint_rows(rows, args.dry_limit)
    elif args.dry_run_xueqiu and args.stock_code:
        rows = fetch_kline_from_xueqiu(
            stock_code=args.stock_code,
            market=args.market,
            bar_count=args.lmt,
        )
        _pprint_rows(rows, args.dry_limit)
    else:
        stats = run_loop(
            market=args.market,
            lmt=args.lmt,
            end_date=args.end,
            min_sleep=args.min_sleep,
            max_sleep=args.max_sleep,
            data_source=args.data_source,
            stock_code=args.stock_code,
        )
        print("完成，统计信息:", stats)
