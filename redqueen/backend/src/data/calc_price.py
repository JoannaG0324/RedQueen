import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, text
import numpy as np
import pandas as pd
from src.utils.config import settings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 数据库连接配置
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME



# 创建数据库连接
engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")


# ==================== 通用计算函数 ====================

def calculate_moving_averages(df, periods=[3, 5, 10, 20, 30, 60, 90, 120, 200]):
    """
    计算移动平均线
    从最新日期开始往前计算，若数据量不足则记为null
    
    Args:
        df: 包含股票数据的DataFrame，需要有'date'和'close'列
        periods: 移动平均线周期列表
        
    Returns:
        dict: 包含各周期移动平均线的字典
    """
    # 确保数据按日期排序（最新的在前）
    df = df.sort_values('date', ascending=False).reset_index(drop=True)
    
    # 初始化结果字典
    ma_results = {}
    
    for period in periods:
        ma_col = f'ma{period}'
        ma_values = []
        
        for i in range(len(df)):
            # 检查是否有足够的数据计算移动平均
            if i + period <= len(df):
                # 计算移动平均（从当前位置往前取period个数据点）
                ma_value = df.iloc[i:i+period]['close'].mean()
                ma_values.append(ma_value)
            else:
                ma_values.append(None)
        
        ma_results[ma_col] = ma_values
    
    return ma_results

def calculate_atr(df, periods=[3, 5, 10, 14]):
    """
    计算ATR (Average True Range)
    从最新日期开始往前计算，若数据量不足则记为null
    
    Args:
        df: 包含股票数据的DataFrame，需要有'date', 'high', 'low', 'close'列
        periods: ATR计算周期列表
        
    Returns:
        dict: 包含各周期ATR的字典
    """
    # 确保数据按日期排序（最新的在前）
    df = df.sort_values('date', ascending=False).reset_index(drop=True)
    
    # 计算True Range
    df['prev_close'] = df['close'].shift(-1)  # 前一日收盘价（因为是倒序，所以用shift(-1)）
    
    # 计算三个候选值
    df['tr1'] = df['high'] - df['low']  # 当日最高价 - 当日最低价
    df['tr2'] = abs(df['high'] - df['prev_close'])  # 当日最高价 - 前日收盘价
    df['tr3'] = abs(df['low'] - df['prev_close'])   # 当日最低价 - 前日收盘价
    
    # True Range是三个值中的最大值
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # 初始化结果字典
    atr_results = {}
    
    for period in periods:
        atr_col = f'atr{period}'
        atr_values = []
        
        for i in range(len(df)):
            # 检查是否有足够的数据计算ATR
            if i + period <= len(df):
                # 计算ATR（从当前位置往前取period个数据点的TR平均值）
                atr_value = df.iloc[i:i+period]['tr'].mean()
                atr_values.append(atr_value)
            else:
                atr_values.append(None)
        
        atr_results[atr_col] = atr_values
    
    return atr_results

def calculate_growth_streak(df):
    """
    计算个股持续增长天数及增长比例
    从最新日期开始往前计算，统计连续上涨的天数和累计涨幅
    
    Args:
        df: 包含股票数据的DataFrame，需要有'date'和'close'列
        
    Returns:
        dict: 包含持续增长天数和增长比例的字典
    """
    # 确保数据按日期排序（最新的在前）
    df = df.sort_values('date', ascending=False).reset_index(drop=True)
    
    # 计算每日涨跌幅
    df['prev_close'] = df['close'].shift(-1)  # 前一日收盘价
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    
    # 初始化结果
    growth_streak_days = []  # 持续增长天数（平盘记为0.1天）
    growth_streak_pct = []   # 持续增长累计涨幅（从增长开始到计算日期的涨幅）
    
    # ========= 嵌套循环实现（O(n²)） =========
    for i in range(len(df)):
        current_streak_days = 0.0
        current_streak_pct = 0.0
        
        # 从当前日期开始往前查找连续上涨/平盘
        for j in range(i, len(df)):
            pct_change = df.iloc[j]['pct_change']
            prev_close = df.iloc[j]['prev_close']
            
            # 检查是否有有效的前一日数据
            if pd.isna(prev_close):
                break
                
            if pct_change > 0:  # 上涨
                current_streak_days += 1.0
                # 计算累计涨幅（从连续上涨的第一天到当前日期）
                if j == i:  # 当前日期
                    current_streak_pct = pct_change
                else:
                    # 计算从连续上涨开始到当前日期的累计涨幅
                    start_close = df.iloc[j]['prev_close']  # 连续上涨开始的前一日收盘价
                    end_close = df.iloc[i]['close']  # 当前日期收盘价
                    current_streak_pct = (end_close / start_close - 1) * 100
            elif pct_change == 0:  # 平盘
                current_streak_days += 0.1
                # 平盘不改变累计涨幅，保持之前的累计涨幅
                if j == i:  # 当前日期平盘
                    current_streak_pct = 0.0
            else:  # 下跌
                break
        
        growth_streak_days.append(current_streak_days)
        growth_streak_pct.append(current_streak_pct)

    return {
        'growth_streak_days': growth_streak_days,
        'growth_streak_pct': growth_streak_pct
    }


# ==================== 【个股数据】初始化 处理个股数据并写入数据库 by stock_daily_qfq ====================

def process_stock_indicators(stock_code):
    """
    计算单个股票的指标并写入数据库（一体化函数，包含更新功能）
    
    Args:
        stock_code: 股票代码
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该股票的旧数据（更新模式）
        delete_sql = f"DELETE FROM stock_daily_qfq_calc WHERE stock_code = '{stock_code}'" # by stock_daily_qfq
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询单个股票的数据
        query = f"""
        SELECT stock_code, date, open, close, high, low, volume, amount
        FROM stock_daily_qfq 
        WHERE stock_code = '{stock_code}'
        ORDER BY date DESC
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {stock_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"股票 {stock_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                row_data = {
                    'stock_code': stock_code,
                    'date': df_stock.iloc[i]['date'],
                    'ma3': None,
                    'ma5': None,
                    'ma10': None,
                    'ma20': None,
                    'ma30': None,
                    'ma60': None,
                    'ma90': None,
                    'ma120': None,
                    'ma200': None,
                    'atr3': None,
                    'atr5': None,
                    'atr10': None,
                    'atr14': None
                }
                calc_data.append(row_data)
            
            # 转换为DataFrame
            df_calc = pd.DataFrame(calc_data)
            
            # 存储到数据库（使用append模式）
            df_calc.to_sql('stock_daily_qfq_calc', engine, if_exists='append', 
                          index=False, method='multi')
            
            print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
            return True
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)

        # 计算持续增长天数及增长比例
        growth_results = calculate_growth_streak(df_stock)
        
        # 准备插入数据
        calc_data = []
        for i in range(len(df_stock)):
            row_data = {
                'stock_code': stock_code,
                'date': df_stock.iloc[i]['date'],
            }
            
            # 添加MA数据
            for ma_col, ma_values in ma_results.items():
                row_data[ma_col] = ma_values[i]
            
            # 添加ATR数据
            for atr_col, atr_values in atr_results.items():
                row_data[atr_col] = atr_values[i]

            # 添加持续增长数据
            row_data['growth_streak_days'] = growth_results['growth_streak_days'][i]
            row_data['growth_streak_pct'] = growth_results['growth_streak_pct'][i]
            
            calc_data.append(row_data)
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('stock_daily_qfq_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理股票 {stock_code} 时出现错误: {str(e)}")
        return False
    
    print("计算结果表创建完成")

def calculate_stock_indicators_multithreaded(stock_codes=None, max_workers=10):
    """
    使用多线程计算股票指标（统一函数，支持计算全部股票或指定股票）
    
    Args:
        stock_codes: 股票代码列表，如果为None则计算所有股票
        max_workers: 最大线程数，默认为4
        
    Returns:
        dict: 包含成功和失败统计的字典
    """
        
    try:
        # 创建计算结果表
        # create_calc_table()
        
        if stock_codes is None:
            print(f"stock_codes 为空，不进行计算")
        elif isinstance(stock_codes, str):
            stock_codes = [stock_codes]
            print(f"开始计算指定 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        else:
            print(f"开始批量计算 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_stock = {executor.submit(process_stock_indicators, stock_code): stock_code 
                             for stock_code in stock_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(stock_codes)
            processed = 0
            
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'股票 {stock_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 股票 {stock_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"多线程计算完成！")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票") 
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只股票: {total_time/len(stock_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(stock_codes)
        }
        
    except Exception as e:
        print(f"多线程计算过程中出现错误: {str(e)}")
        raise

# ===== daily update：每日处理函数 =====
def process_daily_stock_indicators(stock_code, target_date):
    """
    处理单个股票的每日指标计算
    
    Args:
        stock_code: 股票代码
        target_date: 目标日期（仅计算这一天的指标）
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该股票在目标日期的旧数据
        delete_sql = f"DELETE FROM stock_daily_qfq_calc WHERE stock_code = '{stock_code}' AND date = '{target_date}'"
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询该股票最近120天的数据（用于指标计算）
        query = f"""
        SELECT stock_code, date, open, close, high, low, volume, amount
        FROM stock_daily_qfq 
        WHERE stock_code = '{stock_code}'
        AND date <= '{target_date}'
        ORDER BY date DESC
        LIMIT 200
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {stock_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"股票 {stock_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                if df_stock.iloc[i]['date'] == target_date:  # 只保存目标日期的数据
                    row_data = {
                        'stock_code': stock_code,
                        'date': df_stock.iloc[i]['date'],
                        'ma3': None,
                        'ma5': None,
                        'ma10': None,
                        'ma20': None,
                        'ma30': None,
                        'ma60': None,
                        'ma90': None,
                        'ma120': None,
                        'ma200': None,
                        'atr3': None,
                        'atr5': None,
                        'atr10': None,
                        'atr14': None
                    }
                    calc_data.append(row_data)
            
            if calc_data:
                # 转换为DataFrame
                df_calc = pd.DataFrame(calc_data)
                
                # 存储到数据库（使用append模式）
                df_calc.to_sql('stock_daily_qfq_calc', engine, if_exists='append', 
                              index=False, method='multi')
                
                # print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
                return True
            else:
                return False
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)

        # 计算持续增长天数及增长比例
        growth_results = calculate_growth_streak(df_stock)
        
        # 准备插入数据（只插入目标日期的数据）
        calc_data = []
        for i in range(len(df_stock)):
            if df_stock.iloc[i]['date'] == target_date:
                row_data = {
                    'stock_code': stock_code,
                    'date': df_stock.iloc[i]['date'],
                }
                
                # 添加MA数据
                for ma_col, ma_values in ma_results.items():
                    row_data[ma_col] = ma_values[i]
                
                # 添加ATR数据
                for atr_col, atr_values in atr_results.items():
                    row_data[atr_col] = atr_values[i]

                # 添加持续增长数据
                row_data['growth_streak_days'] = growth_results['growth_streak_days'][i]
                row_data['growth_streak_pct'] = growth_results['growth_streak_pct'][i]
                
                calc_data.append(row_data)
        
        if not calc_data:
            print(f"股票 {stock_code} 在目标日期 {target_date} 没有数据")
            return False
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('stock_daily_qfq_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        # print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理股票 {stock_code} 时出现错误: {str(e)}")
        return False

def daily_process_stock_indicators(max_workers=10):
    """
    每日处理函数：更新当天全部个股的指标数据
    
    功能说明：
    1. 获取stock_daily_qfq表中的最新日期
    2. 获取该日期所有有数据的股票代码
    3. 为每只股票获取最近120天的数据（用于指标计算）
    4. 计算这些股票的最新指标（仅最新日期）
    5. 将计算结果存入stock_daily_qfq_calc表
    
    Args:
        max_workers: 最大线程数，默认为10
        
    Returns:
        dict: 包含处理结果的统计信息
    """
    try:
        print("==== 每日指标计算处理 stock_daily_qfq_calc ====")
        print("开始每日指标计算处理...")
        
        # 获取最新日期
        latest_date_query = "SELECT MAX(date) as latest_date FROM stock_daily_qfq"
        latest_date_df = pd.read_sql(latest_date_query, engine)
        latest_date = latest_date_df.iloc[0]['latest_date']
        
        if latest_date is None:
            print("未找到有效日期数据，请先更新stock_daily_qfq表")
            return None
            
        print(f"最新数据日期: {latest_date}")
        
        # 获取该日期所有有数据的股票代码
        stock_codes_query = f"""
        SELECT DISTINCT stock_code 
        FROM stock_daily_qfq 
        WHERE date = '{latest_date}'
        """
        stock_codes_df = pd.read_sql(stock_codes_query, engine)
        stock_codes = stock_codes_df['stock_code'].tolist()
        
        print(f"共找到 {len(stock_codes)} 只股票在 {latest_date} 有数据")
        
        if not stock_codes:
            print("未找到任何股票数据")
            return None
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_stock = {executor.submit(process_daily_stock_indicators, stock_code, latest_date): stock_code 
                             for stock_code in stock_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(stock_codes)
            processed = 0
            
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'股票 {stock_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 股票 {stock_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"\n每日处理完成！日期: {latest_date}")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票")
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只股票: {total_time/len(stock_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(stock_codes)
        }
        
    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise

# ==================== 【行业数据】初始化 处理行业数据并写入数据库 by industry_ths_index ====================

def process_industry_indicators(stock_code):
    """
    计算单个股票的指标并写入数据库（一体化函数，包含更新功能）
    
    Args:
        stock_code: 股票代码
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该股票的旧数据（更新模式）!update
        delete_sql = f"DELETE FROM industry_ths_index_calc WHERE industry_code = '{stock_code}'" # by industry_ths_index !update
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询单个股票的数据
        query = f"""
        SELECT industry_code, date, open, close, high, low, volume, amount
        FROM industry_ths_index
        WHERE industry_code = '{stock_code}'
        ORDER BY date DESC
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {stock_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"股票 {stock_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                row_data = {
                    'industry_code': stock_code, #!update
                    'date': df_stock.iloc[i]['date'],
                    'ma3': None,
                    'ma5': None,
                    'ma10': None,
                    'ma20': None,
                    'ma30': None,
                    'ma60': None,
                    'ma90': None,
                    'ma120': None,
                    'ma200': None,
                    'atr3': None,
                    'atr5': None,
                    'atr10': None,
                    'atr14': None
                }
                calc_data.append(row_data)
            
            # 转换为DataFrame
            df_calc = pd.DataFrame(calc_data)
            
            # 存储到数据库（使用append模式）
            df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', #!update
                          index=False, method='multi')
            
            print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
            return True
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)
        
        # 准备插入数据
        calc_data = []
        for i in range(len(df_stock)):
            row_data = {
                'industry_code': stock_code, #!update
                'date': df_stock.iloc[i]['date'],
            }
            
            # 添加MA数据
            for ma_col, ma_values in ma_results.items():
                row_data[ma_col] = ma_values[i]
            
            # 添加ATR数据
            for atr_col, atr_values in atr_results.items():
                row_data[atr_col] = atr_values[i]
            
            calc_data.append(row_data)
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        print(f"股票 {stock_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理股票 {stock_code} 时出现错误: {str(e)}")
        return False
    
    print("计算结果表创建完成")

def calculate_industry_indicators_multithreaded(stock_codes=None, max_workers=10):
    """
    使用多线程计算股票指标（统一函数，支持计算全部股票或指定股票）
    
    Args:
        stock_codes: 股票代码列表，如果为None则计算所有股票
        max_workers: 最大线程数，默认为4
        
    Returns:
        dict: 包含成功和失败统计的字典
    """
        
    try:
        # 创建计算结果表
        # create_calc_table()
        
        if stock_codes is None:
            print(f"stock_codes 为空，不进行计算")
        elif isinstance(stock_codes, str):
            stock_codes = [stock_codes]
            print(f"开始计算指定 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        else:
            print(f"开始批量计算 {len(stock_codes)} 只股票的指标，使用 {max_workers} 个线程")
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_stock = {executor.submit(process_industry_indicators, stock_code): stock_code 
                             for stock_code in stock_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(stock_codes)
            processed = 0
            
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'股票 {stock_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 股票 {stock_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"多线程计算完成！")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票") 
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只股票: {total_time/len(stock_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(stock_codes)
        }
        
    except Exception as e:
        print(f"多线程计算过程中出现错误: {str(e)}")
        raise

# ===== daily update：每日处理函数 =====
def process_daily_industry_indicators(industry_code, target_date):
    """
    处理单个行业的每日指标计算
    
    Args:
        industry_code: 行业代码
        target_date: 目标日期（仅计算这一天的指标）
        
    Returns:
        bool: 处理是否成功
    """
    try:
        # 先删除该行业在目标日期的旧数据
        delete_sql = f"DELETE FROM industry_ths_index_calc WHERE industry_code = '{industry_code}' AND date = '{target_date}'"
        with engine.begin() as conn:
            conn.execute(text(delete_sql))
        
        # 查询该行业最近120天的数据（用于指标计算）
        query = f"""
        SELECT industry_code, date, open, close, high, low, volume, amount
        FROM industry_ths_index
        WHERE industry_code = '{industry_code}'
        AND date <= '{target_date}'
        ORDER BY date DESC
        LIMIT 200
        """
        
        df_stock = pd.read_sql(query, engine)
        
        if df_stock.empty:
            print(f"股票 {industry_code} 没有找到数据")
            return False
        
        if len(df_stock) < 3:  # 至少需要3天数据
            print(f"行业 {industry_code} 数据不足（仅{len(df_stock)}条），所有计算指标存入NULL值")
            # 数据不足时，将所有计算指标设置为NULL，但仍然保存基础数据
            calc_data = []
            for i in range(len(df_stock)):
                if df_stock.iloc[i]['date'] == target_date:  # latest date
                # if str(df_stock.iloc[i]['date']) == str(target_date):  # 【1-指定日期计算】
                    row_data = {
                        'industry_code': industry_code,
                        'date': df_stock.iloc[i]['date'],
                        'ma3': None,
                        'ma5': None,
                        'ma10': None,
                        'ma20': None,
                        'ma30': None,
                        'ma60': None,
                        'ma90': None,
                        'ma120': None,
                        'ma200': None,
                        'atr3': None,
                        'atr5': None,
                        'atr10': None,
                        'atr14': None
                    }
                    calc_data.append(row_data)
            
            if calc_data:
                # 转换为DataFrame
                df_calc = pd.DataFrame(calc_data)
                
                # 存储到数据库（使用append模式）
                df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                              index=False, method='multi')
                
                # print(f"行业 {industry_code} 更新完成，共处理 {len(df_calc)} 条记录（指标为NULL）")
                return True
            else:
                return False
        
        # 计算移动平均线
        ma_results = calculate_moving_averages(df_stock)
        
        # 计算ATR
        atr_results = calculate_atr(df_stock)
        
        # 准备插入数据（只插入目标日期的数据）
        calc_data = []
        for i in range(len(df_stock)):
            if df_stock.iloc[i]['date'] == target_date: # latest date
            # if str(df_stock.iloc[i]['date']) == str(target_date): # 【1-指定日期计算】
                row_data = {
                    'industry_code': industry_code,
                    'date': df_stock.iloc[i]['date'],
                }
                
                # 添加MA数据
                for ma_col, ma_values in ma_results.items():
                    row_data[ma_col] = ma_values[i]
                
                # 添加ATR数据
                for atr_col, atr_values in atr_results.items():
                    row_data[atr_col] = atr_values[i]
                
                calc_data.append(row_data)
        
        if not calc_data:
            print(f"行业 {industry_code} 在目标日期 {target_date} 没有数据")
            return False
        
        # 转换为DataFrame
        df_calc = pd.DataFrame(calc_data)
        
        # 存储到数据库（使用append模式）
        df_calc.to_sql('industry_ths_index_calc', engine, if_exists='append', 
                      index=False, method='multi')
        
        # print(f"行业 {industry_code} 更新完成，共处理 {len(df_calc)} 条记录")
        return True
        
    except Exception as e:
        print(f"处理行业 {industry_code} 时出现错误: {str(e)}")
        return False

def daily_process_industry_indicators(max_workers=10):
    """
    每日处理函数：更新当天全部个股的指标数据
    
    功能说明：
    1. 获取industry_ths_index表中的最新日期
    2. 获取该日期所有有数据的行业代码
    3. 为每个行业获取最近120天的数据（用于指标计算）
    4. 计算这些行业的最新指标（仅最新日期）
    5. 将计算结果存入industry_ths_index_calc表
    
    Args:
        max_workers: 最大线程数，默认为10
        
    Returns:
        dict: 包含处理结果的统计信息
    """
    try:
        print("==== 每日指标计算处理 industry_ths_index_calc ====")
        print("开始每日指标计算处理...")
        
        # latest_date = '2026-04-01'  # 【1-指定日期计算】

        # 获取最新日期
        latest_date_query = "SELECT MAX(date) as latest_date FROM industry_ths_index"
        latest_date_df = pd.read_sql(latest_date_query, engine)
        latest_date = latest_date_df.iloc[0]['latest_date']
        
        if latest_date is None:
            print("未找到有效日期数据，请先更新industry_ths_index表")
            return None
            
        print(f"最新数据日期: {latest_date}")
        
        # 获取该日期所有有数据的股票代码
        industry_codes_query = f"""
        SELECT DISTINCT industry_code 
        FROM industry_ths_index 
        WHERE date = '{latest_date}'
        """
        industry_codes_df = pd.read_sql(industry_codes_query, engine)
        industry_codes = industry_codes_df['industry_code'].tolist()
        
        print(f"共找到 {len(industry_codes)} 只行业在 {latest_date} 有数据")
        
        if not industry_codes:
            print("未找到任何行业数据")
            return None
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_industry = {executor.submit(process_daily_industry_indicators, industry_code, latest_date): industry_code 
                             for industry_code in industry_codes}
            
            # 收集结果
            successful = 0
            failed = 0
            total_count = len(industry_codes)
            processed = 0
            
            for future in as_completed(future_to_industry):
                industry_code = future_to_industry[future]
                processed += 1
                try:
                    result = future.result()
                    if result:
                        successful += 1
                    else:
                        failed += 1
                except Exception as exc:
                    print(f'行业 {industry_code} 处理时发生异常: {exc}')
                    failed += 1
                
                # 打印进度（在同一行更新）
                print(f"\r{processed}/{total_count} 行业 {industry_code} 处理完成", end="", flush=True)
        
        # 计算总耗时
        total_time = time.time() - start_time
        
        print(f"\n每日处理完成！日期: {latest_date}")
        print(f"成功: {successful} 只股票")
        print(f"失败: {failed} 只股票")
        print(f"总耗时: {total_time:.2f} 秒")
        print(f"平均每只行业: {total_time/len(industry_codes):.2f} 秒")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'average_time': total_time/len(industry_codes)
        }
        
    except Exception as e:
        print(f"每日处理过程中出现错误: {str(e)}")
        raise


if __name__ == "__main__":
    # -------------------- 个股指标计算 --------------------

    # 全量数据计算
    # all_stock_query = f"""
    #  SELECT DISTINCT stock_code FROM stock_daily_qfq WHERE date = (select MAX(date) from stock_daily_qfq) 
    # """
    # all_stock_df = pd.read_sql(all_stock_query, engine)
    # all_stock = all_stock_df['stock_code'].tolist()
    
    # # 测试多线程批量计算
    # calculate_stock_indicators_multithreaded(all_stock, max_workers=10)
    
    # 测试每日处理功能
    daily_process_stock_indicators(max_workers=10)

    # -------------------- 行业指标计算 --------------------

    # 全量数据计算
    # all_stock_query = f"""
    #  SELECT DISTINCT industry_code FROM industry_ths_index WHERE date = (select MAX(date) from industry_ths_index) 
    # """
    # all_stock_df = pd.read_sql(all_stock_query, engine)
    # all_stock = all_stock_df['industry_code'].tolist()
    
    # 测试多线程批量计算
    # calculate_industry_indicators_multithreaded(all_stock, max_workers=10)

    daily_process_industry_indicators(max_workers=10)
