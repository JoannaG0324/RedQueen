"""
交易日执行，更新行业股票列表
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import akshare as ak
import pandas as pd
from urllib.parse import urlencode
from sqlalchemy import create_engine, text, Date, String, DECIMAL, BigInteger
from src.utils.config import settings
import requests 
import json
import concurrent.futures
import time
import random
from typing import Dict, Any, Optional
import tqdm
from time import sleep
from selenium import webdriver # 导入 WebDriver 类
from selenium.webdriver.chrome.options import Options # 导入 Chrome 选项类
from selenium.webdriver.common.by import By # 导入 By 类，用于定位元素
from selenium.webdriver.chrome.service import Service


# 数据库配置
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

def setup_chrome_driver():
    """
    设置Chrome浏览器驱动
    """
    # 创建 Chrome 选项对象，用于配置浏览器启动参数
    chrome_options = Options()
    # 设置自定义 User-Agent，伪装成真实浏览器（Mac Chrome 141）
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36')
    # 禁用 Chrome 的沙箱机制，提升兼容性（常用于 Linux 或容器环境）
    chrome_options.add_argument('--no-sandbox')
    # 避免使用 /dev/shm 共享内存，防止内存不足导致的崩溃
    chrome_options.add_argument('--disable-dev-shm-usage')
    # 禁用 Blink 引擎的自动化控制特性，降低被检测为爬虫的风险
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    # 注释掉无头模式，以便使用已登录的浏览器会话（可见窗口方便调试）
    # chrome_options.add_argument('--headless')
    # 从 Chrome 启动参数中排除 "enable-automation" 开关，进一步隐藏自动化特征
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # 禁用 Chrome 的自动化扩展，防止其暴露 WebDriver 身份
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # 关键参数：保持窗口开启
    chrome_options.add_experimental_option("detach", True)
    # 启用多标签页支持
    chrome_options.add_argument("--new-window")

    
    # 使用上述选项启动 Chrome 浏览器实例
    # Try to find local driver first
    driver_path = os.path.join(os.getcwd(), 'drivers', 'chromedriver-mac-arm64', 'chromedriver')
    if not os.path.exists(driver_path):
        # Try checking in drivers/chromedriver-mac-arm64/chromedriver (sometimes cwd varies)
        driver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'drivers', 'chromedriver-mac-arm64', 'chromedriver')

    if os.path.exists(driver_path):
        print(f"Using local chromedriver at: {driver_path}")
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        print("Local chromedriver not found, trying default (Selenium Manager)...")
        driver = webdriver.Chrome(options=chrome_options)

    # 通过 JavaScript 重写 navigator.webdriver 属性为 undefined，进一步伪装成真实用户浏览器
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# history
def fetch_industry_ths_data_history(industry_code: str, driver=None, close_previous_tab=True) -> Optional[pd.DataFrame]:
    """
    获取行业板块的K线数据（支持多标签页）
    
    Args:
        industry_code: 行业代码
        driver: 可选的WebDriver实例，如果为None则创建新的
        close_previous_tab: 是否在处理完成后关闭前一个标签页
    """
    if driver is None:
        driver = setup_chrome_driver()
    url = f"https://d.10jqka.com.cn/v4/line/bk_{industry_code}/01/2026.js"
    driver.get(url)

    try:
        # 原始内容
        data = driver.find_element(By.TAG_NAME, "pre").text
        #
        json_start = data.find('(') + 1
        json_end = data.rfind(')')
        json_str = data[json_start:json_end]
        json_data = json.loads(json_str)

        # 提取data字段中的K线数据
        data_str = json_data.get('data', '')

        # 解析K线数据
        records = []

        for day_data in data_str.split(';'):
            if not day_data.strip():
                continue

            data = day_data.split(',')

            record = {
                'date': data[0],
                'industry_code': industry_code,
                'open': float(data[1]) if data[1] else None,
                'high': float(data[2]) if data[2] else None,
                'low': float(data[3]) if data[3] else None,
                'close': float(data[4]) if data[4] else None,
                'volume': int(data[5]) if data[5] else None,  # 成交量(手)
                'amount': float(data[6]) if data[6] else None,  # 成交额(元)
            }
            records.append(record)
        
        df = pd.DataFrame(records)
        return df



    except Exception as e:
        print(f"行业板块 {industry_code} 获取数据时出错: {e}")
        
        return None

def save_to_db_history(industry_data: pd.DataFrame):
    """
    更新行业板块的K线数据到数据库
    """
    if industry_data is None or industry_data.empty:
        print("没有数据可更新")
        return

    # 转换日期列为日期类型
    industry_data['date'] = pd.to_datetime(industry_data['date'])

    # 批量插入数据
    try:
        with engine.begin() as conn:
            # 先删除旧数据
            # conn.execute(text("DELETE FROM industry_ths_index WHERE industry_code = :industry_code"),
            #             {'industry_code': industry_data['industry_code'].iloc[0]})
            
            # 批量插入新数据
            industry_data.to_sql('industry_ths_index', conn, if_exists='append', index=False)
        # print(f"成功更新行业板块 {industry_data['industry_code'].iloc[0]} 的K线数据")
    except Exception as e:
        print(f"更新数据库时出错: {e}")

def update_industry_ths_index_history():
    """
    更新行业板块的K线数据索引（使用多标签页优化）
    """
    # 行业代码列表（示例）
    # industry_codes = ["881124", "881121", "881122", "881123"]  # 可以替换为从数据库查询的实际行业代码

    # 查询数据库中的行业代码
    query = text("select distinct industry_code from industry_ths")
    with engine.connect() as conn:
        results = conn.execute(query)
        industry_codes = [row[0] for row in results.fetchall()]

    # 创建浏览器驱动实例
    driver = setup_chrome_driver()
    
    temp_df =[]
    try:
        for i, industry_code in enumerate(tqdm.tqdm(industry_codes, desc="更新行业板块K线数据")):
            # 获取行业板块的K线数据（使用多标签页）
            temp_record = fetch_industry_ths_data_history(
                industry_code=industry_code,
                driver=driver,
                close_previous_tab=(i > 0)  # 第一个标签页不关闭前一个
            )
            temp_df.append(temp_record)
            
            # 添加随机延迟，避免请求过于频繁
            sleep(random.uniform(1, 5))
            # sleep(20)

        # 正确合并所有行业的数据
        if temp_df:
            temp_df = pd.concat(temp_df, ignore_index=True)
        else:
            temp_df = pd.DataFrame()

        if temp_df is not None and not temp_df.empty:
            # 使用现有的 save_to_db 函数保存数据
            save_to_db_history(temp_df)

    
    finally:
        # 确保最终关闭浏览器
        try:
            driver.quit()
        except:
            pass

# daily
def fetch_industry_ths_data_daily(industry_code: str, driver=None, close_previous_tab=True) -> Optional[pd.DataFrame]:
    """
    获取行业板块的K线数据（支持多标签页）
    
    Args:
        industry_code: 行业代码
        driver: 可选的WebDriver实例，如果为None则创建新的
        close_previous_tab: 是否在处理完成后关闭前一个标签页
    """
    if driver is None:
        driver = setup_chrome_driver()
    url = f"https://d.10jqka.com.cn/v4/line/bk_{industry_code}/01/today.js"
    driver.get(url)

    try:
        # 原始内容
        data = driver.find_element(By.TAG_NAME, "pre").text
        
        # 解析JSON数据
        json_start = data.find('(') + 1
        json_end = data.rfind(')')
        json_str = data[json_start:json_end]
        json_data = json.loads(json_str)

        # 根据新的数据格式提取字段
        # 格式: quotebridge_v4_line_bk_881140_01_today({"bk_881140":{"1":"20251107","7":"6898.764","8":"6936.363","9":"6869.272","11":"6879.456","13":2227365200,"19":"36776023000.000",...}})
        
        # 获取行业数据对象
        industry_key = f"bk_{industry_code}"
        industry_data = json_data.get(industry_key, {})
        
        # 解析单个交易日数据
        record = {
            'date': industry_data.get('1', ''),  # 1-date
            'industry_code': industry_code,
            'open': float(industry_data.get('7', 0)) if industry_data.get('7') else None,  # 7-open
            'high': float(industry_data.get('8', 0)) if industry_data.get('8') else None,   # 8-high
            'low': float(industry_data.get('9', 0)) if industry_data.get('9') else None,   # 9-low
            'close': float(industry_data.get('11', 0)) if industry_data.get('11') else None,  # 11-close
            'volume': int(industry_data.get('13', 0)) if industry_data.get('13') else None,  # 13-volume
            'amount': float(industry_data.get('19', 0)) if industry_data.get('19') else None,  # 19-amount
        }
        
        return record



    except Exception as e:
        print(f"行业板块 {industry_code} 获取数据时出错: {e}")
        
        return None

def save_to_db_daily(industry_data: pd.DataFrame):
    """
    更新行业板块的K线数据到数据库
    """
    if industry_data is None or industry_data.empty:
        print("没有数据可更新")
        return

    # 转换日期列为日期类型
    industry_data['date'] = pd.to_datetime(industry_data['date']).dt.strftime('%Y-%m-%d')

    # 批量插入数据
    try:
        with engine.begin() as conn:
            # 先删除旧数据 （根据日期删除）
            conn.execute(text("DELETE FROM industry_ths_index WHERE date = :date"),
                        {'date': industry_data['date'].iloc[0]})    
            
            # 批量插入新数据
            industry_data.to_sql('industry_ths_index', conn, if_exists='append', index=False)
        # print(f"成功更新行业板块 {industry_data['industry_code'].iloc[0]} 的K线数据")
    except Exception as e:
        print(f"更新数据库时出错: {e}")

def update_industry_ths_index_daily():
    """
    更新行业板块的K线数据索引（使用多标签页优化）
    """
    # 行业代码列表（示例）
    # industry_codes = ["881124", "881121", "881122", "881123"]  # 可以替换为从数据库查询的实际行业代码

    # 查询数据库中的行业代码
    query = text("select distinct industry_code from industry_ths")
    with engine.connect() as conn:
        results = conn.execute(query)
        industry_codes = [row[0] for row in results.fetchall()]

    # 创建浏览器驱动实例
    driver = setup_chrome_driver()
    
    temp_df =[]
    try:
        for i, industry_code in enumerate(tqdm.tqdm(industry_codes, desc="更新行业板块K线数据")):
            temp_record = fetch_industry_ths_data_daily(
                industry_code=industry_code,
                driver=driver
            )
            temp_df.append(temp_record)
            sleep(random.uniform(1, 5))

        # 正确合并所有行业的数据 - 处理字典类型的返回值
        if temp_df:
            # 过滤掉 None 值，然后将字典转换为 DataFrame
            valid_records = [record for record in temp_df if record is not None]
            if valid_records:
                temp_df = pd.DataFrame(valid_records)
            else:
                temp_df = pd.DataFrame()
        else:
            temp_df = pd.DataFrame()

        if temp_df is not None and not temp_df.empty:
            # 使用现有的 save_to_db 函数保存数据
            # save_to_db(temp_df)
            save_to_db_daily(temp_df)
            print(f"数据总量: {len(temp_df)}")
            print(f"实际写入: {len(temp_df)}")

    
    finally:
        # 确保最终关闭浏览器
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    # update_industry_ths_index_history()
    update_industry_ths_index_daily()
