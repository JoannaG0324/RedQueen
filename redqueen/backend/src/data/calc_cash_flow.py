import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from sqlalchemy import create_engine, text
import time
import akshare as ak  
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm  # 导入进度显示模块
import logging
from src.data.calc_price import daily_process_stock_indicators,daily_process_industry_indicators


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义数据库连接信息
from src.utils.config import settings

USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

# 从配置文件中获取数据表名称
STOCK_INFO_TABLE_NAME = 'stock_info'# 股票基础信息  
STOCK_DAILY_TABLE_NAME = 'stock_daily'# 股票日线数据
STOCK_PRICE_RESULTS_TABLE_NAME = 'stock_price_results'# 股票计算结果
SCORE_INDUSTRY_TABLE_NAME = 'score_industry'# 股票评分  

# 创建数据库连接引擎
engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

# 更新股票基础信息表
def get_stock_info(engine):
    """
    Replace: 更新并覆盖股票基础信息表 
    
    """
    try:
        # 获取上海市场股票信息
        sh_stock_info = ak.stock_info_sh_name_code()
        sh_stock_info = sh_stock_info[['证券代码', '证券简称', '上市日期']]
        sh_stock_info.rename(columns={
            '证券代码': 'stock_code',
            '证券简称': 'stock_name',
            '上市日期': 'ipo_date'
        }, inplace=True)
        sh_stock_info.loc[:, 'market'] = "sh"
        
        # 获取深圳市场股票信息
        sz_stock_info = ak.stock_info_sz_name_code()
        sz_stock_info = sz_stock_info[['A股代码', 'A股简称', 'A股上市日期']]
        sz_stock_info.rename(columns={
            'A股代码': 'stock_code',
            'A股简称': 'stock_name',
            'A股上市日期': 'ipo_date'
        }, inplace=True)
        # 修改为使用.loc明确指定
        sz_stock_info.loc[:, 'market'] = "sz"
        
        # 合并上海和深圳市场的数据
        stock_info = pd.concat([sh_stock_info, sz_stock_info], ignore_index=True)
        
        # 覆盖写入到数据库中的股票基础信息表
        stock_info.to_sql(STOCK_INFO_TABLE_NAME, con=engine, if_exists='replace', index=False)
        return f"Update Success: '{STOCK_INFO_TABLE_NAME}'"

    except Exception as e:
        return f"更新股票基础信息时发生错误: {e}"

# [切换到GetStockData.py]daily price update_1: 获取单只股票的历史数据：访问数据接口
def fetch_stock_history(full_stock_code, start_date, end_date):
    """
    获取单只股票的历史数据

    :param full_stock_code: str - 包含市场代码的完整股票代码
    :param start_date: str - 获取数据的开始日期，格式为'YYYYMMDD'
    :param end_date: str - 获取数据的结束日期，格式为'YYYYMMDD'
    :return: Tuple[pd.DataFrame, str] - 包含历史数据的DataFrame和操作结果的描述信息
    """
    # time.sleep(2)
    try:
        stock_history = ak.stock_zh_a_daily(symbol=full_stock_code, start_date=start_date, end_date=end_date, adjust="qfq")
        if stock_history is not None and not stock_history.empty:
            stock_history['stock_code'] = full_stock_code  # 存入完整的股票代码（包含市场代码）
            return stock_history, f"历史数据获取成功: {full_stock_code}."
        else:
            return None, f"没有新的历史数据: {full_stock_code}"
    except Exception as e:
        return None, f"获取 {full_stock_code} 的历史数据时发生错误: {e}"    

# [切换到GetStockData.py]daily price update_2: 更新所有股票的股价数据
def get_stock_history(engine, end_date):
    """
    Append: 更新所有股票的股价数据，并将新数据批量追加到股价数据表中

    :param engine: SQLAlchemy Engine - 数据库引擎。
    :param end_date: str - 获取数据的结束日期，格式为'YYYYMMDD'，默认为今天
    :return: str - 操作结果的描述信息。
    """
    if end_date is None:
        end_date = pd.Timestamp.today().strftime('%Y%m%d')
    
    try:
        # 获取数据库中所有的股票代码及市场信息
        stock_info_df = pd.read_sql(f"SELECT stock_code, market FROM {STOCK_INFO_TABLE_NAME}", con=engine)
        print(stock_info_df.shape)

        # # 获取stock_daily表中的最新日期作为start_date
        # latest_date_query = f"SELECT MAX(date) FROM {STOCK_DAILY_TABLE_NAME}"
        # latest_date = pd.read_sql(latest_date_query, con=engine).iloc[0, 0]

        # # 常规更新：检查数据当前日期，并以最新日期作为开始日期
        # if latest_date is None:
        #     # 如果表中没有记录，默认从2024年1月1日开始
        #     start_date = '20230101'
        # else:
        #     start_date = (latest_date + pd.Timedelta(days=1)).strftime('%Y%m%d')
        #     # print(start_date)

        # 手动更新：直接定义开始日期
        start_date = '20230101'    

        operation_messages = []  # 存储每只股票的处理结果信息

        # 使用tqdm显示进度条
        with ThreadPoolExecutor(max_workers=10) as executor:  # 设置线程池大小
            futures = []
            for index, row in stock_info_df.iterrows():
                stock_code = row['stock_code']
                market = row['market']
                full_stock_code = f"{market}{stock_code}"
                futures.append(executor.submit(fetch_stock_history, full_stock_code, start_date, end_date))

            for future in tqdm(futures, desc="Fetching and saving stock history"):
                stock_history, message = future.result()  # 获取数据和消息
                operation_messages.append(message)  # 保存操作消息
                # print(message)
                if stock_history is not None and not stock_history.empty:
                    # 直接写入数据库
                    stock_history.to_sql(STOCK_DAILY_TABLE_NAME, con=engine, if_exists='append', index=False)

        return f"Update Success: '{STOCK_DAILY_TABLE_NAME}'"

    except Exception as e:
        return f"更新股票历史数据时发生错误: {e}"

# 计算价格 version1：计算给定股价数据的 20 日均价和 14 日 ATR，并将结果写入数据库
def calculate_price(engine, ma_window_1=20, ma_window_2=10, atr_window=14):
    """
    从数据库读取股价数据，计算给定股价数据的 20 日均价、10 日均价和 14 日 ATR，并将结果写入数据库。

    参数:
    engine : SQLAlchemy Engine - 数据库引擎
    ma_window_1 : int - 计算 20 日均价的窗口大小，默认为 20。
    ma_window_2 : int - 计算 10 日均价的窗口大小，默认为 10。
    atr_window : int - 计算 ATR 的窗口大小，默认为 14。
    
    返回:
    str - 操作结果的描述信息。
    """
    try:
        # 读取 `stock_daily` 表数据
        query = f"SELECT * FROM {STOCK_DAILY_TABLE_NAME}"
        stock_daily_df = pd.read_sql(query, engine)

        # 移除 `stock_code` 中的市场代码（如 'sh', 'sz' 等）
        stock_daily_df['stock_code'] = stock_daily_df['stock_code'].apply(lambda x: x[2:])

        # 按股票代码分组计算必要的列
        stock_daily_df['high_low'] = stock_daily_df.groupby('stock_code')['high'].transform(lambda x: x - stock_daily_df['low'])
        stock_daily_df['high_close'] = stock_daily_df.groupby('stock_code')['high'].transform(lambda x: (x - stock_daily_df['close'].shift()).abs())
        stock_daily_df['low_close'] = stock_daily_df.groupby('stock_code')['low'].transform(lambda x: (x - stock_daily_df['close'].shift()).abs())

        # 计算 TR
        stock_daily_df['TR'] = stock_daily_df[['high_low', 'high_close', 'low_close']].max(axis=1)

        # 按股票代码分组计算 20 日均价
        stock_daily_df['20_day_ma'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: x.rolling(window=ma_window_1).mean())

        # 按股票代码分组计算 10 日均价
        stock_daily_df['10_day_ma'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: x.rolling(window=ma_window_2).mean())

        # 新增四个价格变动百分比指标
        stock_daily_df['pre_price_60'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(60) - 1).fillna(0))
        stock_daily_df['pre_price_30'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(30) - 1).fillna(0))
        stock_daily_df['pre_price_20'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(20) - 1).fillna(0))
        stock_daily_df['pre_price_10'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(10) - 1).fillna(0))

        # 按股票代码分组计算 ATR
        stock_daily_df['ATR'] = stock_daily_df.groupby('stock_code')['TR'].transform(lambda x: x.rolling(window=atr_window).mean())

        # 计算 stock_score
        stock_daily_df['stock_score'] = ((stock_daily_df['close'] >= stock_daily_df['20_day_ma']) & stock_daily_df['20_day_ma'].notna()).astype(int)
        
        # 计算 stock_score_ma10
        stock_daily_df['stock_score_ma10'] = ((stock_daily_df['close'] >= stock_daily_df['10_day_ma']) & stock_daily_df['10_day_ma'].notna()).astype(int)

        # 选择需要输出的列
        result_df = stock_daily_df[['date', 'stock_code', '20_day_ma', '10_day_ma', 'ATR', 'stock_score', 'stock_score_ma10', 'pre_price_60', 'pre_price_30', 'pre_price_20', 'pre_price_10']]

        print("Caculating...")
        # 写入数据库
        result_df.to_sql(STOCK_PRICE_RESULTS_TABLE_NAME, con=engine, if_exists='replace', index=False)

        return f"Update Success: {STOCK_PRICE_RESULTS_TABLE_NAME}"

    except Exception as e:
        return f"Error in calculate_price: {e}"

# 【股价指标计算】计算价格 version2：计算最新日期的价格指标，并更新到结果表中
def calculate_price_latest(engine, ma_window_1=20, ma_window_2=10, atr_window=14):
    """
    从数据库读取最新日期的股价数据，计算该日期的 20 日均价、10 日均价和 14 日 ATR，并更新到结果表中。
    
    性能优化：只读取计算所需的最少历史数据，而非全部历史数据，显著提升计算效率。
    数据需求分析：
    - 60日价格变动百分比：需要61天数据（当前日期+前60天）
    - 20日均价：需要20天数据
    - 10日均价：需要10天数据  
    - 14日ATR：需要15天数据（因为需要前一日收盘价计算TR）
    实际获取：max(61, ma_window_1, atr_window + 1) 天数据

    参数:
    engine : SQLAlchemy Engine - 数据库引擎
    ma_window_1 : int - 计算 20 日均价的窗口大小，默认为 20。
    ma_window_2 : int - 计算 10 日均价的窗口大小，默认为 10。
    atr_window : int - 计算 ATR 的窗口大小，默认为 14。
    
    返回:
    str - 操作结果的描述信息。
    """
    print(" === Caculating the price indicators === ")

    try:
        # 获取最新日期
        latest_date_query = f"SELECT MAX(date) as latest_date FROM {STOCK_DAILY_TABLE_NAME}"
        latest_date_df = pd.read_sql(latest_date_query, con=engine)
        latest_date = latest_date_df['latest_date'].iloc[0]
        
        if latest_date is None:
            return "Error: No data found in stock_daily table"
            
        print(f"Processing data for latest date: {latest_date}")
        
        # 计算需要的最大历史数据天数
        # 60日价格变动百分比需要61天数据（当前日期+前60天）
        # 20日均价需要20天数据
        # 14日ATR需要15天数据（因为需要前一日收盘价计算TR）
        max_days_needed = max(100, ma_window_1, atr_window + 1)
        
        # 只读取必要的历史数据以计算滚动指标
        query = f"""
        SELECT * FROM (
            SELECT *, 
                   ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY date DESC) as rn
            FROM {STOCK_DAILY_TABLE_NAME}
            WHERE date <= '{latest_date}'
        ) t 
        WHERE rn <= {max_days_needed}
        ORDER BY stock_code, date
        """
        stock_daily_df = pd.read_sql(query, engine)
        
        # 移除 `stock_code` 中的市场代码（如 'sh', 'sz' 等）
        # stock_daily_df['stock_code'] = stock_daily_df['stock_code'].apply(lambda x: x[2:])
        
        # 按股票代码分组计算必要的列
        stock_daily_df['high_low'] = stock_daily_df.groupby('stock_code')['high'].transform(lambda x: x - stock_daily_df['low'])
        stock_daily_df['high_close'] = stock_daily_df.groupby('stock_code').apply(lambda x: (x['high'] - x['close'].shift()).abs()).reset_index(drop=True)
        stock_daily_df['low_close'] = stock_daily_df.groupby('stock_code').apply(lambda x: (x['low'] - x['close'].shift()).abs()).reset_index(drop=True)
        
        # 计算 TR
        stock_daily_df['TR'] = stock_daily_df[['high_low', 'high_close', 'low_close']].max(axis=1)
        
        # 按股票代码分组计算 20 日均价
        stock_daily_df['20_day_ma'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: x.rolling(window=ma_window_1).mean())
        
        # 按股票代码分组计算 10 日均价
        stock_daily_df['10_day_ma'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: x.rolling(window=ma_window_2).mean())
        
        # 新增四个价格变动百分比指标
        stock_daily_df['pre_price_60'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(60) - 1).fillna(0))
        stock_daily_df['pre_price_30'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(30) - 1).fillna(0))
        stock_daily_df['pre_price_20'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(20) - 1).fillna(0))
        stock_daily_df['pre_price_10'] = stock_daily_df.groupby('stock_code')['close'].transform(lambda x: (x/x.shift(10) - 1).fillna(0))
        
        # 按股票代码分组计算 ATR
        stock_daily_df['ATR'] = stock_daily_df.groupby('stock_code')['TR'].transform(lambda x: x.rolling(window=atr_window).mean())
        
        # 计算 stock_score
        stock_daily_df['stock_score'] = ((stock_daily_df['close'] >= stock_daily_df['20_day_ma']) & stock_daily_df['20_day_ma'].notna()).astype(int)
        
        # 计算 stock_score_ma10
        stock_daily_df['stock_score_ma10'] = ((stock_daily_df['close'] >= stock_daily_df['10_day_ma']) & stock_daily_df['10_day_ma'].notna()).astype(int)
        
        # 筛选最新日期的数据
        latest_result_df = stock_daily_df[stock_daily_df['date'] == latest_date]
        
        # 选择需要输出的列
        latest_result_df = latest_result_df[['date', 'stock_code', '20_day_ma', '10_day_ma', 'ATR', 'stock_score', 'stock_score_ma10', 'pre_price_60', 'pre_price_30', 'pre_price_20', 'pre_price_10']]
        
        # 检查是否有最新日期的数据
        if latest_result_df.empty:
            return f"No data found for date: {latest_date}"
            
        # 从结果表中删除最新日期的数据（如果存在）
        delete_query = f"DELETE FROM {STOCK_PRICE_RESULTS_TABLE_NAME} WHERE date = '{latest_date}'"
        with engine.connect() as connection:
            connection.execute(text(delete_query))
            connection.commit()
        
        # 将最新日期的数据写入结果表
        latest_result_df.to_sql(STOCK_PRICE_RESULTS_TABLE_NAME, con=engine, if_exists='append', index=False)

        print('Caculating the price indicators done')

        
        # return f"Update Success: {STOCK_PRICE_RESULTS_TABLE_NAME} for date {latest_date}, {len(latest_result_df)} records updated"
        
    except Exception as e:
        print(f"Error in calculate_price_latest: {e}")

# 【行业得分计算】重新计算行业得分：计算行业得分，并将结果写入数据库
def score_industry(com_ind_df, engine):
    """
    Replace: 计算行业得分

    :param com_ind_df: 包含个股与行业关联的数据框。
    :param engine: SQLAlchemy Engine - 数据库引擎。
    :return: str - 操作结果的描述信息。
    """
    print(" === Caculating the industry score === ")

    try:
        # 从数据库中读取 calculate_price_df
        calculate_price_df = pd.read_sql(f"SELECT * FROM {STOCK_PRICE_RESULTS_TABLE_NAME}", engine)

        # 合并个股得分与行业数据
        merged_df = calculate_price_df.merge(
            com_ind_df[['stock_code', 'industry_level_1_name', 'industry_level_2_name']], 
            on='stock_code', 
            how='left'
        )

        # 按日期和二级行业计算得分
        industry_scores = (merged_df.groupby(['date', 'industry_level_1_name', 'industry_level_2_name'])
            .agg(industry_score=('stock_score', 'sum'),
                 industry_score_sum=('stock_score', 'count'),
                 industry_score_ma10=('stock_score_ma10', 'sum'),
                 industry_score_sum_ma10=('stock_score_ma10', 'count'))
            .reset_index()
        )

        # 计算行业得分比例
        industry_scores['industry_score_pct'] = industry_scores['industry_score'] / industry_scores['industry_score_sum'].replace(0, pd.NA)
        industry_scores['industry_score_pct_ma10'] = industry_scores['industry_score_ma10'] / industry_scores['industry_score_sum_ma10'].replace(0, pd.NA)
        
        score_industry_df = industry_scores[['date', 'industry_level_1_name', 'industry_level_2_name', 'industry_score', 'industry_score_sum', 'industry_score_pct', 'industry_score_ma10', 'industry_score_sum_ma10', 'industry_score_pct_ma10']]
        # 将结果写入数据库
        score_industry_df.to_sql(SCORE_INDUSTRY_TABLE_NAME, con=engine, if_exists='replace', index=False)

        # return f"Update Success: '{SCORE_INDUSTRY_TABLE_NAME}'"
        print('Caculating the industry score done')


    except Exception as e:
        print(f"Score industry calculation failed: {e}")

# 创建中证800与行业分类的关系并返回合并后的DataFrame    
def fetch_com_ind_relation(engine):
    """
    创建中证800与行业分类的关系并返回合并后的DataFrame。

    参数:
    engine : SQLAlchemy Engine - 数据库引擎

    返回:
    DataFrame - 包含中证800成分股及其行业分类的关系
    """
    # 查询中证800成分股的SQL语句
    query_components = """
    SELECT 
        stock_code,
        stock_name
    FROM 
        csindex_800_components;
    """

    # 查询个股关联行业的SQL语句
    query_industry = """
    SELECT 
        stock_code,
        industry_level_1_name,
        industry_level_2_name,
        industry_level_3_name,
        industry_level_4_name
    FROM 
        csindex_industry;
    """

    # 使用Pandas读取查询结果到DataFrame
    components_df = pd.read_sql(query_components, engine)
    industry_df = pd.read_sql(query_industry, engine)

    # 合并两个DataFrame
    com_ind_df = pd.merge(components_df, industry_df, on='stock_code', how='left')

    return com_ind_df

# 【行业净流入计算】计算行业现金流指标 3天/5天/10天/20天合计值
def industry_flow_calc(engine):
    """
    计算行业现金流的3天/5天/10天/20天的移动平均值
    
    计算逻辑：
    1. 根据表industry_flow_ODS数据的最新日期
    2. 计算每个行业的前N（3/5/10/20）个数据之和
    3. 若数据数量<N，则记null
    4. 将结果存入表industry_flow_calc，使用industry_code关联industry_ths表
    
    Parameters:
        engine: SQLAlchemy Engine - 数据库引擎
        
    Returns:
        str: 操作结果的描述信息
    """
    print(" === Caculating the industry flow indicators === ")

    try:
        # 查询industry_flow_ODS表获取数据
        query = """
        SELECT industry_name, net_inflow, date 
        FROM industry_flow_ODS 
        ORDER BY date DESC, industry_name
        """
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return "industry_flow_ODS表中没有数据，无法计算"
        
        # 获取industry_ths表的行业代码映射
        industry_mapping_query = "SELECT industry_code, industry_name FROM industry_ths WHERE flag = 1"
        industry_mapping = pd.read_sql(industry_mapping_query, engine)
        
        if industry_mapping.empty:
            return "industry_ths表中没有有效的行业代码映射，无法继续"
        
        # 合并行业代码信息
        df_with_code = df.merge(industry_mapping, on='industry_name', how='left')
        
        # 获取最新的日期
        latest_date = df['date'].max()
        logger.info(f"最新日期: {latest_date}")
        
        # 按行业代码分组，计算移动平均值
        result_data = []
        
        for industry_code in df_with_code['industry_code'].unique():
            if pd.isna(industry_code):
                continue
                
            industry_df = df_with_code[df_with_code['industry_code'] == industry_code].sort_values('date', ascending=False)
            industry_name = industry_df['industry_name'].iloc[0] if not industry_df.empty else ""
            
            # 计算不同时间窗口的移动平均值
            ma_windows = [2, 3, 5, 10, 20]
            ma_results = {}
            
            for window in ma_windows:
                if len(industry_df) >= window:
                    # 取前window个数据的net_inflow之和
                    ma_value = industry_df['net_inflow'].head(window).sum()
                else:
                    ma_value = None
                ma_results[f'net_inflow_ma{window}'] = ma_value
            
            # 添加结果
            result_data.append({
                'date': latest_date,
                'industry_code': industry_code,
                'industry_name': industry_name,
                'net_inflow': industry_df['net_inflow'].iloc[0] if not industry_df.empty else None,
                **ma_results
            })
        
        # 创建结果DataFrame
        result_df = pd.DataFrame(result_data)
        
        # 保存到industry_flow_calc表
        result_df.to_sql('industry_flow_calc', con=engine, if_exists='append', index=False)
        
        # return f"行业现金流计算完成，共处理{len(result_df)}个行业，最新日期: {latest_date}"
        print(f"行业现金流计算完成，共处理{len(result_df)}个行业，最新日期: {latest_date}")
        
    except Exception as e:
        # return f"行业现金流计算失败: {e}"
        print(f"行业现金流计算失败: {e}")

# 【行业净流入计算-临时版本】计算全量数据的行业现金流指标
def industry_flow_calc_full(engine):
    """
    计算行业现金流的3天/5天/10天/20天的移动平均值（全量数据版本）
    
    计算逻辑：
    1. 获取industry_flow_ODS表的所有数据
    2. 为每个行业、每个日期计算前N（3/5/10/20）个数据的移动平均值
    3. 若数据数量<N，则记null
    4. 将结果存入表industry_flow_calc_full，使用industry_code关联industry_ths表
    
    Parameters:
        engine: SQLAlchemy Engine - 数据库引擎
        
    Returns:
        str: 操作结果的描述信息
    """
    try:
        # 查询industry_flow_ODS表获取所有数据
        query = """
        SELECT industry_name, net_inflow, date 
        FROM industry_flow_ODS 
        ORDER BY industry_name, date DESC
        """
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return "industry_flow_ODS表中没有数据，无法计算"
        
        # 获取industry_ths表的行业代码映射
        industry_mapping_query = "SELECT industry_code, industry_name FROM industry_ths WHERE flag = 1"
        industry_mapping = pd.read_sql(industry_mapping_query, engine)
        
        if industry_mapping.empty:
            return "industry_ths表中没有有效的行业代码映射，无法继续"
        
        # 合并行业代码信息
        df_with_code = df.merge(industry_mapping, on='industry_name', how='left')
        
        # 按行业代码和日期分组，计算移动平均值
        result_data = []
        
        for industry_code in df_with_code['industry_code'].unique():
            if pd.isna(industry_code):
                continue
                
            industry_df = df_with_code[df_with_code['industry_code'] == industry_code].sort_values('date', ascending=False)
            industry_name = industry_df['industry_name'].iloc[0] if not industry_df.empty else ""
            
            # 为每个日期计算移动平均值
            for idx, row in industry_df.iterrows():
                current_date = row['date']
                current_net_inflow = row['net_inflow']
                
                # 获取当前日期之前的数据（包括当前日期）
                data_up_to_date = industry_df[industry_df['date'] <= current_date].sort_values('date', ascending=False)
                
                # 计算不同时间窗口的移动平均值
                ma_windows = [3, 5, 10, 20]
                ma_results = {}
                
                for window in ma_windows:
                    if len(data_up_to_date) >= window:
                        # 取前window个数据的net_inflow之和
                        ma_value = data_up_to_date['net_inflow'].head(window).sum()
                    else:
                        ma_value = None
                    ma_results[f'net_inflow_ma{window}'] = ma_value
                
                # 添加结果
                result_data.append({
                    'date': current_date,
                    'industry_code': industry_code,
                    'industry_name': industry_name,
                    'net_inflow': current_net_inflow,
                    **ma_results
                })
        
        # 创建结果DataFrame
        result_df = pd.DataFrame(result_data)
        
        # 保存到industry_flow_calc_full表
        result_df.to_sql('industry_flow_calc', con=engine, if_exists='replace', index=False)
        
        return f"行业现金流全量计算完成，共处理{len(result_df)}条记录，涵盖{len(result_df['date'].unique())}个日期"
        
    except Exception as e:
        return f"行业现金流全量计算失败: {e}"

# 数据更新：更新所有股票的股价数据、计算价格、重新计算行业得分
# def data_upate(latest_only=False):
#     """
#     更新数据并计算指标
    
#     参数:
#     latest_only : bool - 是否只计算最新日期的数据，默认为 False。
    
#     返回:
#     list - 操作结果的描述信息列表。
#     """
#     messages = []
    
    # # 1. 更新股票基础信息
    # msg = get_stock_info(engine)
    # messages.append(msg)

    # # 2. 获取当前日期
    # end_date = pd.Timestamp.today().strftime('%Y%m%d')
    # end_date = '20250717'
    # # print(end_date)
    # print('start calculating...')


    # 3. 更新所有股票的股价数据
    # print("fetch data")
    # msg = get_stock_history(engine, end_date)
    # messages.append(msg)

    # start




if __name__ == "__main__":
    # # 1. 计算个股价格
    # latest_only = True
    # if latest_only:
    #     # 只计算最新日期的数据
    #     calculate_price_latest(engine)
    # else:
    #     # 计算所有日期的数据
    #     calculate_price(engine)   

    # # 2. 重新计算行业得分
    # score_industry(fetch_com_ind_relation(engine),engine)

    ###############
    # # 3. 计算行业现金流指标
    industry_flow_calc(engine)

    # # 4. 更新股票基础技术指标
    daily_process_stock_indicators(max_workers=10)

    # # 5. 更新行业基础技术指标
    daily_process_industry_indicators(max_workers=10)

    ###############
    # # 6. 计算策略指标
    # results, stock_stats_df = strategy_calc()
    # save_to_sql_temp(results, stock_stats_df) 

