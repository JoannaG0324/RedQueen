"""获取概念板块数据:搜狐
从搜狐获取概念板块数据并存储到数据库
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import json
import re
from sqlalchemy import create_engine, text
from src.utils.config import settings
from datetime import date

USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")


def parse_number(value):
    if value is None:
        return None
    s = str(value).strip()
    if s == '':
        return None
    s = s.replace(',', '')
    s = s.replace('+', '')
    if s.endswith('%'):
        s = s[:-1]
    try:
        if '.' in s:
            return float(s)
        else:
            return int(s)
    except ValueError:
        return None


def parse_stock_code(full_code):
    if full_code is None:
        return None
    s = str(full_code).strip()
    if s.startswith('cn_'):
        return s[3:]
    return s


def update_concept_plate():
    """
    获取概念板块数据并存储到数据库
    数据源: https://q.stock.sohu.com/pl/pl-1.html
    
    Returns:
        str/bool: 成功返回消息，失败返回False
    """
    print("=== 开始获取概念板块数据: concept_plate_data ===")
    
    # url = "https://q.stock.sohu.com/pl/pl-1.html?uid=1782810418778cebgwp&437360320841"
    url = "https://q.stock.sohu.com/pl/pl-1630.html?uid=1782810418778cebgwp&538880007939"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6) Chrome/130.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        full_html = resp.text
    except Exception as e:
        print(f"❌ 请求异常：{e}")
        return False

    start_pos = full_html.find("PEAK_ODIA(['pllist',")
    if start_pos == -1:
        print("❌ HTML中未找到PEAK_ODIA数据入口")
        return False

    slice_html = full_html[start_pos:]
    stack = 0
    end_index = None
    for idx, char in enumerate(slice_html):
        if char == '[':
            stack += 1
        elif char == ']':
            stack -= 1
            if stack == 0:
                end_index = idx + 1
                break
    if end_index is None:
        print("❌ 未匹配到完整数组")
        return False

    raw_js_arr = slice_html[:end_index].replace("PEAK_ODIA(", "").rstrip(")")
    json_text = raw_js_arr.replace("'", '"')
    
    try:
        full_raw = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败：{e}")
        return False

    stock_list = []
    
    for concept_fields in full_raw[1:]:
        if not isinstance(concept_fields, list) or len(concept_fields) < 13:
            continue
        
        stock = {
            "concept_id": concept_fields[0],
            "concept_name": concept_fields[1],
            "stock_count": parse_number(concept_fields[2]),
            "avg_price": parse_number(concept_fields[3]),
            "avg_change_amount": parse_number(concept_fields[4]),
            "avg_change_ratio": parse_number(concept_fields[5]),
            "total_volume": parse_number(concept_fields[6]),
            "total_amount": parse_number(concept_fields[7]),
            "top_stock_code": parse_stock_code(concept_fields[8]),
            "top_stock_name": concept_fields[9],
            "top_stock_price": parse_number(concept_fields[10]),
            "top_stock_change_amount": parse_number(concept_fields[11]),
            "top_stock_change_ratio": parse_number(concept_fields[12]),
            "date": date.today()
        }
        stock_list.append(stock)
    
    if not stock_list:
        print("警告: 获取的数据为空")
        return False
    
    print(f"解析到 {len(stock_list)} 条概念板块数据")

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS `concept_plate_data` (
        `id` int NOT NULL AUTO_INCREMENT COMMENT '自增序号',
        `concept_id` varchar(20) DEFAULT NULL COMMENT '概念id',
        `concept_name` varchar(100) DEFAULT NULL COMMENT '概念板块名称',
        `stock_count` int DEFAULT NULL COMMENT '概念个股数量',
        `avg_price` decimal(10,2) DEFAULT NULL COMMENT '平均价格',
        `avg_change_amount` decimal(10,2) DEFAULT NULL COMMENT '平均涨跌额',
        `avg_change_ratio` decimal(10,2) DEFAULT NULL COMMENT '平均涨跌幅(%)',
        `total_volume` bigint DEFAULT NULL COMMENT '总手',
        `total_amount` bigint DEFAULT NULL COMMENT '总成交金额',
        `top_stock_code` varchar(10) DEFAULT NULL COMMENT '领涨股代码(去除cn_前缀)',
        `top_stock_name` varchar(50) DEFAULT NULL COMMENT '领涨股名称',
        `top_stock_price` decimal(10,2) DEFAULT NULL COMMENT '领涨股当前价',
        `top_stock_change_amount` decimal(10,2) DEFAULT NULL COMMENT '领涨股涨跌额',
        `top_stock_change_ratio` decimal(10,2) DEFAULT NULL COMMENT '领涨股涨跌幅(%)',
        `date` date DEFAULT NULL COMMENT '交易日期',
        `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (`id`),
        INDEX `idx_concept_name` (`concept_name`),
        INDEX `idx_top_stock_code` (`top_stock_code`),
        INDEX `idx_date` (`date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='概念板块数据(搜狐来源)'
    """

    with engine.connect() as conn:
        conn.execute(text(create_table_sql))

    today = date.today()
    delete_sql = text("DELETE FROM concept_plate_data WHERE date = :date")
    
    with engine.connect() as conn:
        result = conn.execute(delete_sql, {"date": today})
        deleted_rows = result.rowcount
        
    if deleted_rows > 0:
        print(f"删除了 {deleted_rows} 条当天的旧数据")

    insert_sql = text("""
        INSERT INTO concept_plate_data (
            concept_id, concept_name, stock_count, avg_price, avg_change_amount, avg_change_ratio,
            total_volume, total_amount, top_stock_code, top_stock_name,
            top_stock_price, top_stock_change_amount, top_stock_change_ratio, date
        ) VALUES (
            :concept_id, :concept_name, :stock_count, :avg_price, :avg_change_amount, :avg_change_ratio,
            :total_volume, :total_amount, :top_stock_code, :top_stock_name,
            :top_stock_price, :top_stock_change_amount, :top_stock_change_ratio, :date
        )
    """)

    with engine.connect() as conn:
        for stock in stock_list:
            conn.execute(insert_sql, stock)
        conn.commit()

    message = f"成功插入 {len(stock_list)} 条概念板块数据到 concept_plate_data 表"
    print(message)
    
    return message


if __name__ == "__main__":
    result = update_concept_plate()
    if result:
        print(result)
    else:
        print("任务执行失败")