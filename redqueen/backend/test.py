import sys
import os
import re
import json
from datetime import date, datetime
from sqlalchemy import create_engine, text
import pymysql

# --- 配置区域 ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.config import settings
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

FILE_PATH = "/Users/joeg/Desktop/App/RedQueen/raw_data--.txt" # 你的文件路径


# --- 数据处理函数 ---
def parse_number(value):
    if value is None:
        return None
    s = str(value).strip()
    if s == '' or s.lower() == 'null':
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

# --- 主程序 ---
def main():
    success_count = 0
    error_count = 0
    
    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            # 1. 数据清洗与格式化
            # 移除多余的换行符和空格
            content = re.sub(r'\s+', ' ', content)
            
            # 2. 解析数据
            # 由于文件是由多个独立的 [] 数组组成，我们使用正则来分割
            # 匹配以 [ 开头，] 结尾的数组
            matches = re.findall(r'\[.*?\]', content)
            data_list = []
            
            for match in matches:
                try:
                    # 将匹配到的字符串转换为 Python 列表
                    row = json.loads(match)
                    data_list.append(row)
                except json.JSONDecodeError as e:
                    print(f"行数据解析失败: {match[:20]}... 错误: {e}")
                    error_count += 1
                    continue
            
            print(f"成功读取 {len(data_list)} 条概念板块数据。")
            
            # 3. 准备插入数据
            insert_data = []
            # 根据数据内容和你的需求，固定日期为 2026-07-01
            target_date = date(2026, 7, 1) 
            
            for row in data_list:
                try:
                    # 检查字段数量
                    if len(row) < 12:
                        print(f"数据字段不足，跳过: {row}")
                        error_count += 1
                        continue
                    
                    record = {
                        'concept_id': row[0],
                        'concept_name': row[1],
                        'stock_count': parse_number(row[2]),
                        'avg_price': parse_number(row[3]),
                        'avg_change_amount': parse_number(row[4]),
                        'avg_change_ratio': parse_number(row[5]),
                        'total_volume': parse_number(row[6]),
                        'total_amount': parse_number(row[7]) if row[7] != "null" else None,
                        'top_stock_code': parse_stock_code(row[8]),
                        'top_stock_name': row[9],
                        'top_stock_price': parse_number(row[10]),
                        'top_stock_change_amount': parse_number(row[11]),
                        'top_stock_change_ratio': parse_number(row[12]),
                        'date': target_date
                    }
                    
                    insert_data.append(record)
                    success_count += 1
                    
                except Exception as e:
                    print(f"处理数据行出错: {e}")
                    error_count += 1
                    continue
            
            # 4. 批量写入数据库
            if insert_data:
                with engine.connect() as conn:
                    query = text("""
                        INSERT INTO concept_plate_data 
                        (concept_id, concept_name, stock_count, avg_price, avg_change_amount, avg_change_ratio, 
                         total_volume, total_amount, top_stock_code, top_stock_name, top_stock_price, 
                         top_stock_change_amount, top_stock_change_ratio, date)
                        VALUES 
                        (:concept_id, :concept_name, :stock_count, :avg_price, :avg_change_amount, :avg_change_ratio,
                         :total_volume, :total_amount, :top_stock_code, :top_stock_name, :top_stock_price,
                         :top_stock_change_amount, :top_stock_change_ratio, :date)
                    """)
                    
                    conn.execute(query, insert_data)
                    conn.commit()
                    print(f"成功插入 {len(insert_data)} 条记录到数据库。")
            else:
                print("没有有效数据可以插入。")
    
    except FileNotFoundError:
        print(f"错误：找不到文件 {FILE_PATH}")
    except Exception as e:
        print(f"程序执行出错: {e}")
    
    print(f"处理完成。成功: {success_count}, 失败: {error_count}")

if __name__ == "__main__":
    main()