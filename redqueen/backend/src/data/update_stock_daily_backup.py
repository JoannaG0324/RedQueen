import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import pandas as pd
import math
import time
from urllib.parse import urlencode
import json
import random
from tqdm import tqdm
from sqlalchemy import create_engine, text, Date, String, DECIMAL, BigInteger
import pymysql
from src.utils.config import settings
from datetime import date, datetime



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

def fetch_stock_data_selenium():
    """使用Selenium获取股票数据"""
    # 使用已经定义好的setup_chrome_driver函数创建driver实例
    driver = setup_chrome_driver()
    
    # 基础URL - 东方财富行情中心
    base_url = "https://quote.eastmoney.com/center/gridlist.html#hs_a_board"
    print(f"第一步：打开基础URL: {base_url}")
    
    driver.get(base_url)
    
    # 等待页面加载完成
    time.sleep(5)
    
    # 1. 获取总页数 - 在<div class="qtpager">标签中找到title=下一页的前一个标签
    try:
        # 找到分页器
        pager_div = driver.find_element(By.CLASS_NAME, "qtpager")
        
        # 找到所有分页按钮
        page_buttons = pager_div.find_elements(By.TAG_NAME, "a")
        
        # 找到"下一页"按钮
        next_page_button = None
        for button in page_buttons:
            if button.get_attribute("title") == "下一页":
                next_page_button = button
                break
        
        if next_page_button:
            # 找到"下一页"前一个按钮（即最后一页按钮）
            next_page_index = page_buttons.index(next_page_button)
            if next_page_index > 0:
                last_page_button = page_buttons[next_page_index - 1]
                total_pages = int(last_page_button.text)
                print(f"总页数: {total_pages}")
            else:
                print("无法找到最后一页按钮")
                return False
        else:
            print("无法找到下一页按钮")
            return False
            
    except Exception as e:
        print(f"获取分页信息失败: {e}")
        return False

    # 2. 获取当前页的表格数据
    all_data = []
    
    # 从指定页码开始处理
    for current_page in range(start_page, total_pages + 1):
        # 分页信息无需打印
        # print(f"\r正在处理第 {current_page}/{total_pages} 页",end="",flush=True)

        # 如果是第一页，已经加载了，否则需要点击分页
        if current_page > 1:
            try:
                # 首先检查是否有覆盖层阻挡，如果有则关闭
                try:
                    overlay = driver.find_element(By.XPATH, "//div[contains(@style, 'position: fixed') and contains(@style, 'z-index: 99998')]")
                    if overlay:
                        print("检测到覆盖层，尝试关闭...")
                        # 尝试点击覆盖层以外的区域来关闭
                        body = driver.find_element(By.TAG_NAME, "body")
                        body.click()
                        time.sleep(1)
                except:
                    pass  # 没有覆盖层，继续正常操作
                
                # 点击对应的分页按钮
                pager_div = driver.find_element(By.CLASS_NAME, "qtpager")
                page_buttons = pager_div.find_elements(By.TAG_NAME, "a")
                
                # 找到当前页的按钮
                target_button = None
                for button in page_buttons:
                    if button.text == str(current_page):
                        target_button = button
                        break
                
                if target_button:
                    # 使用JavaScript点击，避免元素被遮挡的问题
                    driver.execute_script("arguments[0].click();", target_button)
                    time.sleep(3)  # 等待页面加载
                else:
                    print(f"未找到第 {current_page} 页的按钮")
                    
            except Exception as e:
                print(f"切换第 {current_page} 页失败: {e}")
                # 尝试使用URL直接跳转
                try:
                    page_url = f"{base_url}&pn={current_page}"
                    driver.get(page_url)
                    time.sleep(3)
                    print(f"通过URL直接跳转到第 {current_page} 页")
                except:
                    continue
        
        # 提取表格数据
        try:
            # 找到表格容器
            table_container = driver.find_element(By.CLASS_NAME, "quotetable")
            table = table_container.find_element(By.TAG_NAME, "table")
            
            # 获取表头
            headers = []
            header_row = table.find_element(By.TAG_NAME, "thead").find_element(By.TAG_NAME, "tr")
            header_cells = header_row.find_elements(By.TAG_NAME, "th")
            for cell in header_cells:
                headers.append(cell.text.strip())
            
            # 获取表格数据
            tbody = table.find_element(By.TAG_NAME, "tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                row_data = {}
                for i, cell in enumerate(cells):
                    if i < len(headers):
                        row_data[headers[i]] = cell.text.strip()
                all_data.append(row_data)
                
            print(f"第 {current_page} 页获取到 {len(rows)} 行数据")
            
        except Exception as e:
            print(f"提取第 {current_page} 页表格数据失败: {e}")
            return False
        

    
    # 将数据转换为DataFrame
    if all_data:
        df = pd.DataFrame(all_data)
        print(f"总共获取到 {len(df)} 行数据")
        return df
    else:
        print("未获取到任何数据")
        return pd.DataFrame()

def fetch_stock_data_selenium_plus(start_page, end_page=None):
    """使用Selenium获取股票数据，支持从指定页码开始处理，可选指定结束页码"""
    # 使用已经定义好的setup_chrome_driver函数创建driver实例
    driver = setup_chrome_driver()
    
    # 基础URL - 东方财富行情中心
    base_url = "https://quote.eastmoney.com/center/gridlist.html#hs_a_board"
    print(f"第一步：打开基础URL: {base_url}")
    
    driver.get(base_url)
    
    # 等待页面加载完成
    time.sleep(20)
    
    # 如果指定了起始页码且不是第一页，直接跳转到指定页码
    if start_page > 1:
        print(f"跳转到第 {start_page} 页开始处理...")
        try:
            # 查找分页输入框和GO按钮
            goto_form = driver.find_element(By.CLASS_NAME, "gotoform")
            
            # 查找所有input元素，找到页码输入框和GO按钮
            inputs = goto_form.find_elements(By.TAG_NAME, "input")
            
            page_input = None
            go_button = None
            
            for input_element in inputs:
                input_type = input_element.get_attribute("type")
                input_value = input_element.get_attribute("value")
                
                if input_type == "text" or input_type == "number":
                    page_input = input_element
                elif input_type == "submit" or (input_value and "GO" in input_value.upper()):
                    go_button = input_element
            
            if not page_input or not go_button:
                raise Exception("未找到页码输入框或GO按钮")
            
            # 清空输入框并输入页码
            page_input.clear()
            page_input.send_keys(str(start_page))
            
            # 点击GO按钮 - 使用JavaScript点击确保可靠性
            driver.execute_script("arguments[0].click();", go_button)
            
            # 等待表格数据加载完成
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "quotetable"))
                )
                print(f"成功跳转到第 {start_page} 页，数据加载完成")
            except:
                print(f"第 {start_page} 页数据加载超时，继续尝试")
                time.sleep(3)
            
        except Exception as e:
            print(f"跳转到第 {start_page} 页失败: {e}")
            print("将尝试使用URL直接跳转...")
            
    # 1. 获取总页数 - 在<div class="qtpager">标签中找到title=下一页的前一个标签
    try:
        # 找到分页器
        pager_div = driver.find_element(By.CLASS_NAME, "qtpager")
        
        # 找到所有分页按钮
        page_buttons = pager_div.find_elements(By.TAG_NAME, "a")
        
        # 找到"下一页"按钮
        next_page_button = None
        for button in page_buttons:
            if button.get_attribute("title") == "下一页":
                next_page_button = button
                break
        
        if next_page_button:
            # 找到"下一页"前一个按钮（即最后一页按钮）
            next_page_index = page_buttons.index(next_page_button)
            if next_page_index > 0:
                last_page_button = page_buttons[next_page_index - 1]
                total_pages = int(last_page_button.text)
                print(f"总页数: {total_pages}")
            else:
                print("无法找到最后一页按钮")
                return False
        else:
            print("无法找到下一页按钮")
            return False
            
    except Exception as e:
        print(f"获取分页信息失败: {e}")
        return False

    # 2. 获取当前页的表格数据
    all_data = []
    
    # 如果指定了结束页码，则使用指定的结束页码
    # 否则使用页面上实际获取的total_pages
    if end_page is not None:
        total_pages = end_page
    # 如果没有指定结束页码，保留页面上获取的实际总页数
    # 这样选择"251-"时会从251页到实际的最后一页

    # total_pages + 1
    for current_page in range(start_page, total_pages + 1):
        random_sleep = random.uniform(0.5, 2.0)
        time.sleep(random_sleep)
        # 分页信息无需打印
        # print(f"\r正在处理第 {current_page}/{total_pages} 页",end="",flush=True)

        # 如果是第一页，已经加载了，否则需要点击分页
        if current_page > 1:
            try:
                # 首先检查是否有覆盖层阻挡，如果有则关闭
                try:
                    overlay = driver.find_element(By.XPATH, "//div[contains(@style, 'position: fixed') and contains(@style, 'z-index: 99998')]")
                    if overlay:
                        print("检测到覆盖层，尝试关闭...")
                        # 尝试点击覆盖层以外的区域来关闭
                        body = driver.find_element(By.TAG_NAME, "body")
                        body.click()
                        time.sleep(1)
                except:
                    pass  # 没有覆盖层，继续正常操作
                
                # 点击对应的分页按钮
                pager_div = driver.find_element(By.CLASS_NAME, "qtpager")
                page_buttons = pager_div.find_elements(By.TAG_NAME, "a")
                
                # 找到当前页的按钮
                target_button = None
                for button in page_buttons:
                    if button.text == str(current_page):
                        target_button = button
                        break
                
                if target_button:
                    # 使用JavaScript点击，避免元素被遮挡的问题
                    driver.execute_script("arguments[0].click();", target_button)
                    time.sleep(3)  # 等待页面加载
                else:
                    print(f"未找到第 {current_page} 页的按钮")
                    
            except Exception as e:
                print(f"切换第 {current_page} 页失败: {e}")
        
        # 提取表格数据
        try:
            # 找到表格容器
            table_container = driver.find_element(By.CLASS_NAME, "quotetable")
            table = table_container.find_element(By.TAG_NAME, "table")
            
            # 获取表头
            headers = []
            header_row = table.find_element(By.TAG_NAME, "thead").find_element(By.TAG_NAME, "tr")
            header_cells = header_row.find_elements(By.TAG_NAME, "th")
            for cell in header_cells:
                headers.append(cell.text.strip())
            
            # 获取表格数据
            tbody = table.find_element(By.TAG_NAME, "tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                row_data = {}
                for i, cell in enumerate(cells):
                    if i < len(headers):
                        row_data[headers[i]] = cell.text.strip()
                all_data.append(row_data)
                
            print(f"第 {current_page} 页获取到 {len(rows)} 行数据")
            
        except Exception as e:
            print(f"提取第 {current_page} 页表格数据失败: {e}")
            return False
        

    
    # 将数据转换为DataFrame
    if all_data:
        df = pd.DataFrame(all_data)
        print(f"总共获取到 {len(df)} 行数据")
        return df
    else:
        print("未获取到任何数据")
        return pd.DataFrame()

def process_stock_daily(start_page=1, end_page=None):
    """更新股票日线数据"""
    temp_df = fetch_stock_data_selenium_plus(start_page=start_page, end_page=end_page) #1-51-101-151-201-251
    
    # 根据实际数据结构重命名列
    column_mapping = {
        '序号': 'id',
        '代码': 'stock_code', 
        '名称': 'stock_name',
        '最新价': 'close',
        '涨跌幅': 'change_rate',
        '涨跌额': 'change_amount',
        '成交量(手)': 'volume',
        '成交额': 'amount',
        '振幅': 'amplitude',
        '最高': 'high',
        '最低': 'low',
        '今开': 'open',
        '昨收': 'pre_close',
        '量比': 'volume_ratio',
        '换手率': 'turnover',
        '市盈率(动态)': 'pe_dynamic',
        '市净率': 'pb'
    }
    
    # 重命名列
    temp_df.rename(columns=column_mapping, inplace=True)
    
    # 选择需要的列（丢弃相关链接、加自选字段）
    temp_df = temp_df[
        [
            'id', 'stock_code', 'stock_name', 'close', 'change_rate', 'change_amount', 'volume', 'amount',
            'amplitude', 'high', 'low', 'open', 'pre_close', 'volume_ratio', 'turnover', 'pe_dynamic', 'pb'
        ]
    ]
    
    temp_df.to_csv('stock_daily_113_200.csv', index=False, encoding='utf-8-sig')
    
    drop_percent_columns = ['change_rate', 'turnover', 'amplitude']
    for col in drop_percent_columns:
        if col in temp_df.columns:
            # 先移除百分比符号，然后处理特殊字符
            temp_df[col] = temp_df[col].str.replace('%', '', regex=False)
            temp_df[col] = temp_df[col].replace('-', pd.NA)
            temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
    
    # 处理成交额字段：转换单位（亿/万）
    def convert_volume(value):
        if isinstance(value, str):
            # 先处理特殊字符，将 '-' 替换为 0
            if value.strip() == '-':
                return 0
            if '亿' in value:
                return float(value.replace('亿', '')) * 100000000
            elif '万' in value:
                return float(value.replace('万', '')) * 10000
            else:
                try:
                    return float(value)
                except:
                    return 0
        else:
            return value
        
    temp_df['volume'] = temp_df['volume'].apply(convert_volume)
    temp_df['amount'] = temp_df['amount'].apply(convert_volume)

        # 数据类型转换
    numeric_columns = [
        'close', 'change_amount', 'volume','amount', 'amplitude', 'high', 'low', 
        'open', 'pre_close', 'volume_ratio', 'pe_dynamic','turnover', 'pb'
    ]
    
    for col in numeric_columns:
        # 先处理特殊字符，将 '-' 替换为 NaN
        if col in temp_df.columns:
            temp_df[col] = temp_df[col].replace('-', pd.NA)
            temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
    
    # 过滤掉close或open为0的行
    temp_df = temp_df[(temp_df['close'] > 0) & (temp_df['open'] > 0)]
    
    print("数据处理完成，数据形状:", temp_df.shape)
    return temp_df

def update_stock_daily(start_page=1, end_page=None):
    """更新股票日线数据"""
    temp_df = process_stock_daily(start_page=start_page, end_page=end_page)
    
    # 检查是否有数据
    if temp_df.empty:
        print("未获取到有效数据，更新终止")
        return
    
    temp_df['date'] = date.today()
    # 增加日期
    # temp_df['date'] = "2025-10-31"

    temp_df.to_sql("stock_daily_qfq_new", engine, if_exists="append", index=False)
    
    # 存入stock_daily_qfq时，不存入id字段
    # temp_df_without_id = temp_df.drop(columns=['id'], errors='ignore')
    # temp_df_without_id.to_sql("stock_daily_qfq", engine, if_exists="append", index=False)

    print(f"成功更新 {len(temp_df)} 条新数据")

    return True

if __name__ == "__main__":
    # fetch_stock_data_selenium(max_pages=3)
    update_stock_daily()




    
