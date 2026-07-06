"""获取ETF数据:Akshare
包含ETF实时数据和历史数据获取功能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import akshare as ak
import pandas as pd
from sqlalchemy import create_engine, text, Date, String, DECIMAL, BigInteger
from src.utils.config import settings
from datetime import date, datetime
from src.data.update_industry_ths_daily import update_industry_ths_index_daily  # 更新行业板块日数据



# 数据库配置
USER = settings.DB_USER
PASSWORD = settings.DB_PASSWORD
HOST = settings.DB_HOST
DATABASE = settings.DB_NAME

engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

# 更新行业板块资金流向数据
def update_industry_flow_data():
    """
    接口: stock_board_industry_summary_ths
    目标地址: https://q.10jqka.com.cn/thshy/
    描述: 同花顺-同花顺行业一览表
    获取行业板块资金流向数据并存储到数据库
    
    Returns:
        bool: 成功返回True，失败返回False
    """
    print("=== 开始获取行业板块资金流向数据: industry_flow_ODS ===")
    
    try:
        # 1. 获取行业板块汇总数据
        print("正在获取行业板块数据...")
        industry_data = ak.stock_board_industry_summary_ths()
        
        if industry_data.empty:
            print("警告: 获取的数据为空")
            return False
        
        
        # 创建处理后的数据副本
        processed_data = industry_data.copy()
        
        # 字段映射字典
        column_mapping = {
            '序号': 'serial_no',
            '板块': 'industry_name', 
            '涨跌幅': 'change_percent',
            '总成交量': 'total_volume',
            '总成交额': 'total_amount',
            '净流入': 'net_inflow',
            '上涨家数': 'up_count',
            '下跌家数': 'down_count',
            '均价': 'avg_price',
            '领涨股': 'top_stock_name',
            '领涨股-涨跌幅': 'top_stock_change'
        }
        
        # 检查哪些字段存在并进行重命名
        available_columns = {}
        for original_col, new_col in column_mapping.items():
            if original_col in processed_data.columns:
                available_columns[original_col] = new_col
            else:
                print(f"警告: 字段 '{original_col}' 不存在于数据中")
        
        # 只保留存在的字段并重命名
        processed_data = processed_data[list(available_columns.keys())].copy()
        processed_data.rename(columns=available_columns, inplace=True)
        
        # 添加交易日期
        processed_data['date'] = date.today()
        
        # 3. 数据库操作
        print("开始数据库操作...")
        
        # 创建表（如果不存在）
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `industry_flow_ODS` (
            `id` int NOT NULL AUTO_INCREMENT COMMENT '自增序号',
            `serial_no` varchar(20) DEFAULT NULL COMMENT '序号/排名',
            `industry_name` varchar(50) DEFAULT NULL COMMENT '行业板块名称',
            `change_percent` decimal(10,2) DEFAULT NULL COMMENT '涨跌幅(%)',
            `total_volume` decimal(15,2) DEFAULT NULL COMMENT '总成交量(万手)',
            `total_amount` decimal(15,2) DEFAULT NULL COMMENT '总成交额(亿元)',
            `net_inflow` decimal(15,2) DEFAULT NULL COMMENT '净流入(亿元)',
            `up_count` int DEFAULT NULL COMMENT '上涨家数',
            `down_count` int DEFAULT NULL COMMENT '下跌家数',
            `avg_price` decimal(10,2) DEFAULT NULL COMMENT '均价(元)',
            `top_stock_name` varchar(50) DEFAULT NULL COMMENT '领涨股名称',
            `top_stock_change` decimal(10,2) DEFAULT NULL COMMENT '领涨股涨跌幅(%)',
            `date` date DEFAULT NULL COMMENT '日期',
            PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业板块资金流向数据'
        """
        
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
        
        
        # 删除当天的旧数据（如果存在）
        today = date.today()
        delete_sql = text("DELETE FROM industry_flow_ODS WHERE date = :date")
        
        with engine.connect() as conn:
            result = conn.execute(delete_sql, {"date": today})
            deleted_rows = result.rowcount
            
        if deleted_rows > 0:
            print(f"删除了 {deleted_rows} 条当天的旧数据")
        
        # 插入新数据
        processed_data.to_sql('industry_flow_ODS', engine, if_exists='append', index=False)
        
        message = f"成功插入 {len(processed_data)} 条行业板块数据到 industry_flow_ODS 表"
        print(message)
        
        return message
        
    except Exception as e:
        print(f"获取行业板块数据时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # finally:
    #     # 关闭数据库连接
    #     engine.dispose()

# 更新股票资金流数据
def update_stock_flow_data(date=None):
    """
    获取个股资金流数据并写入表 stock_daily_flow
    
    Args:
        date: 日期，格式为'YYYYMMDD'，默认为今天
    
    Returns:
        bool: 操作是否成功
    """
    print("=== 开始更新股票资金流数据：stock_daily_flow ===")
    try:
        # 1. 处理默认日期
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        # 2. 获取个股资金流数据
        print(f"开始获取 {date} 的个股资金流数据...")
        stock_fund_flow_individual_df = ak.stock_fund_flow_individual(symbol="即时")
        
        if stock_fund_flow_individual_df.empty:
            print("个股资金流数据为空，跳过保存")
            return False
        
        print(f"获取到 {len(stock_fund_flow_individual_df)} 条个股资金流数据")
        
        # 3. 字段名称映射到英文
        db_columns = {
            '序号': 'serial_number',
            '股票代码': 'stock_code',
            '股票简称': 'stock_name',
            '最新价': 'close',
            '涨跌幅': 'change_rate',
            '换手率': 'turnover',
            '流入资金': 'inflow_amount',
            '流出资金': 'outflow_amount',
            '净额': 'net_amount',
            '成交额': 'total_amount'
        }
        
        # 重命名列
        stock_fund_flow_individual_df = stock_fund_flow_individual_df.rename(columns=db_columns)
        
        # 处理涨跌幅和换手率字段：移除%符号并转换为数值
        if 'change_rate' in stock_fund_flow_individual_df.columns:
            stock_fund_flow_individual_df['change_rate'] = stock_fund_flow_individual_df['change_rate'].astype(str).str.replace('%', '').astype(float) 
        
        if 'turnover' in stock_fund_flow_individual_df.columns:
            stock_fund_flow_individual_df['turnover'] = stock_fund_flow_individual_df['turnover'].astype(str).str.replace('%', '').astype(float)
        
        # 格式化股票代码：确保所有股票代码都是6位数字，不足的前面补零
        if 'stock_code' in stock_fund_flow_individual_df.columns:
            stock_fund_flow_individual_df['stock_code'] = stock_fund_flow_individual_df['stock_code'].astype(str).str.strip()
            stock_fund_flow_individual_df['stock_code'] = stock_fund_flow_individual_df['stock_code'].apply(lambda x: x.zfill(6) if x.isdigit() else x) 
        
        # 4. 添加转换后的数值字段（统一转换为万元单位）
        def convert_amount_to_wan_yuan(amount_str):
            """
            将包含汉字的金额字符串转换为万元单位的数值
            
            Args:
                amount_str: 金额字符串，如 '5.56亿', '6731.50万', '10.45亿'
                
            Returns:
                float: 转换为万元单位的数值
            """
            if pd.isna(amount_str) or amount_str == '':
                return 0.0
                
            try:
                # 提取数字部分，包含可能的负号
                import re
                num_match = re.search(r'-?[\d.]+', str(amount_str))
                if not num_match:
                    return 0.0
                    
                num_value = float(num_match.group())
                
                # 根据单位进行转换
                if '亿' in str(amount_str):
                    return num_value * 10000  # 亿转换为万（1亿 = 10000万）
                elif '万' in str(amount_str):
                    return num_value  # 万保持不变
                else:
                    return num_value / 10000  # 元转换为万（1万 = 10000元）
                    
            except (ValueError, TypeError):
                return 0.0
        
        # 添加转换后的数值字段
        stock_fund_flow_individual_df['inflow_amount_wan'] = stock_fund_flow_individual_df['inflow_amount'].apply(convert_amount_to_wan_yuan)
        stock_fund_flow_individual_df['outflow_amount_wan'] = stock_fund_flow_individual_df['outflow_amount'].apply(convert_amount_to_wan_yuan)
        stock_fund_flow_individual_df['net_amount_wan'] = stock_fund_flow_individual_df['net_amount'].apply(convert_amount_to_wan_yuan)
        stock_fund_flow_individual_df['total_amount_wan'] = stock_fund_flow_individual_df['total_amount'].apply(convert_amount_to_wan_yuan)
        
        # 5. 添加日期字段
        stock_fund_flow_individual_df['date'] = pd.to_datetime(date, format='%Y%m%d').date()
        
        # 5. 创建表（如果不存在）
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `stock_daily_flow` (
            `id` int NOT NULL AUTO_INCREMENT COMMENT '自增主键',
            `serial_number` int DEFAULT NULL COMMENT '序号',
            `stock_code` varchar(10) NOT NULL COMMENT '股票代码',
            `stock_name` varchar(50) DEFAULT NULL COMMENT '股票名称',
            `close` decimal(10,2) DEFAULT NULL COMMENT '最新价',
            `change_rate` decimal(10,4) DEFAULT NULL COMMENT '涨跌幅',
            `turnover` decimal(10,2) DEFAULT NULL COMMENT '换手率',
            `inflow_amount` varchar(50) DEFAULT NULL COMMENT '流入资金（原始）',
            `outflow_amount` varchar(50) DEFAULT NULL COMMENT '流出资金（原始）',
            `net_amount` varchar(50) DEFAULT NULL COMMENT '净额（原始）',
            `total_amount` varchar(50) DEFAULT NULL COMMENT '成交额（原始）',
            `inflow_amount_wan` decimal(15,2) DEFAULT NULL COMMENT '流入资金（万元）',
            `outflow_amount_wan` decimal(15,2) DEFAULT NULL COMMENT '流出资金（万元）',
            `net_amount_wan` decimal(15,2) DEFAULT NULL COMMENT '净额（万元）',
            `total_amount_wan` decimal(15,2) DEFAULT NULL COMMENT '成交额（万元）',
            `date` date NOT NULL COMMENT '日期',
            PRIMARY KEY (`id`),
            KEY `idx_stock_code_date` (`stock_code`, `date`),
            KEY `idx_date` (`date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票每日资金流向数据'
        """
        
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
        
        # 7. 删除当天的旧数据（如果存在）
        delete_sql = text("DELETE FROM stock_daily_flow WHERE date = :date")
        with engine.connect() as conn:
            result = conn.execute(delete_sql, {"date": stock_fund_flow_individual_df['date'].iloc[0]})
            if result.rowcount > 0:
                print(f"删除了 {result.rowcount} 条当天的旧数据")
        
        # 8. 插入新数据
        stock_fund_flow_individual_df.to_sql('stock_daily_flow', engine, if_exists='append', index=False)
        message = f"成功插入 {len(stock_fund_flow_individual_df)} 条数据到 stock_daily_flow 表"
        print(message)
        
        # 关闭数据库连接
        engine.dispose()
        
        return message
        
    except Exception as e:
        print(f"更新个股资金流数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

# 更新股票实时数据
def update_stock_spot_data():
    """
    获取股票实时数据并写入数据库的完整流程
    封装自GetStockData_v2.py的功能
    """
    print("=== 开始更新股票实时数据：stock_daily_qfq_new -> stock_daily_qfq ===")
    try:
        # 获取股票数据
        print("开始获取股票实时数据...")
        stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()

        
        if stock_zh_a_spot_em_df.empty:
            print("股票数据为空，跳过保存")
            return False
        
        print(f"获取到 {len(stock_zh_a_spot_em_df)} 条股票数据")
        
        # 重命名列
        db_columns = {
            '序号': 'id',
            '代码': 'stock_code',
            '名称': 'stock_name',
            '最新价': 'close',
            '涨跌幅': 'change_rate',
            '涨跌额': 'change_amount',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude', 
            '最高': 'high',
            '最低': 'low',
            '今开': 'open',
            '昨收': 'pre_close',
            '量比': 'volume_ratio',
            '换手率': 'turnover',
            '市盈率-动态': 'pe_dynamic',
            '市净率': 'pb',
            '总市值': 'total_market_value',
            '流通市值': 'circulating_market_value',
            '涨速': 'change_speed',
            '5分钟涨跌': '5_minute_change',
            '60日涨跌幅': '60_day_change_rate',
            '年初至今涨跌幅': 'year_change_rate'
        }
        
        # 按照db_columns修改字段名称
        stock_zh_a_spot_em_df = stock_zh_a_spot_em_df.rename(columns=db_columns)
        
        # 添加date字段
        stock_zh_a_spot_em_df['date'] = date.today()
        
        # 将数据插入数据库（如果表不存在会自动创建）
        stock_zh_a_spot_em_df.to_sql('stock_daily_qfq_new', engine, if_exists='append', index=False)
        print(f"成功插入 {len(stock_zh_a_spot_em_df)} 条数据到 stock_daily_qfq_new 表")

        message = f"成功插入 {len(stock_zh_a_spot_em_df)} 条数据到 stock_daily_qfq_new 表"
        return message
        
        # # 同时将数据写入stock_daily_qfq表，只保留该表需要的字段
        # # 创建stock_daily_qfq表所需的数据副本
        # stock_daily_qfq_df = stock_zh_a_spot_em_df.copy()
        
        # # 添加outstanding_share字段，对应circulating_market_value
        # stock_daily_qfq_df['outstanding_share'] = stock_daily_qfq_df['circulating_market_value']
        
        # # 只保留stock_daily_qfq表需要的字段
        # stock_daily_qfq_columns = ['stock_code', 'stock_name', 'date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'amplitude', 'change_rate', 'change_amount', 'turnover']
        # stock_daily_qfq_df = stock_daily_qfq_df[stock_daily_qfq_columns]
        
        # # 过滤停牌股票数据（close > 0）
        # stock_daily_qfq_df = stock_daily_qfq_df[(stock_daily_qfq_df['close'] > 0) & (stock_daily_qfq_df['open'] > 0)]
        
        # # 将数据插入stock_daily_qfq表
        # stock_daily_qfq_df.to_sql('stock_daily_qfq', engine, if_exists='append', index=False)
        # message = f"成功插入 {len(stock_daily_qfq_df)} 条数据到 stock_daily_qfq 表（已过滤停牌股票）"
        # print(message)
        
        # return message
        
    except Exception as e:
        print(f"更新股票实时数据时出错: {e}")
        return False

# 更新股票涨停板数据
def update_stock_ztb_data(date=None):
    """
    获取股票涨停板数据并写入表 stock_daily_ztb
    
    Args:
        date: 日期，格式为'YYYYMMDD'，默认为今天
    
    Returns:
        bool: 操作是否成功
    """
    print("=== 开始更新股票涨停板数据：stock_daily_ztb ===") 
    try:
        # 1. 处理默认日期
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        # 2. 获取涨停板数据
        print(f"开始获取 {date} 的涨停板数据...")
        stock_zt_pool_em_df = ak.stock_zt_pool_em(date=date)
        
        if stock_zt_pool_em_df.empty:
            print("涨停板数据为空，跳过保存")
            return False
        
        print(f"获取到 {len(stock_zt_pool_em_df)} 条涨停板数据")
        
        # 2. 字段名称映射到英文
        db_columns = {
            '序号': 'serial_number',
            '代码': 'stock_code',
            '名称': 'stock_name',
            '涨跌幅': 'change_rate',
            '最新价': 'close',
            '成交额': 'amount',
            '流通市值': 'circulating_market_value',
            '总市值': 'total_market_value',
            '换手率': 'turnover',
            '封板资金': 'sealing_fund',
            '首次封板时间': 'first_sealing_time',
            '最后封板时间': 'last_sealing_time',
            '炸板次数': 'explosion_count',
            '涨停统计': 'limit_up_stats',
            '连板数': 'continuous_boards',
            '所属行业': 'industry_eastmoney'
        }
        
        # 重命名列
        stock_zt_pool_em_df = stock_zt_pool_em_df.rename(columns=db_columns)
        
        # 3. 添加日期字段
        stock_zt_pool_em_df['date'] = pd.to_datetime(date, format='%Y%m%d').date()
        
        
        # 5. 创建表（如果不存在）
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `stock_daily_ztb` (
            `id` int NOT NULL AUTO_INCREMENT COMMENT '自增主键',
            `serial_number` int DEFAULT NULL COMMENT '序号',
            `stock_code` varchar(10) NOT NULL COMMENT '股票代码',
            `stock_name` varchar(50) DEFAULT NULL COMMENT '股票名称',
            `change_rate` decimal(10,4) DEFAULT NULL COMMENT '涨跌幅',
            `close` decimal(10,2) DEFAULT NULL COMMENT '最新价',
            `amount` decimal(15,2) DEFAULT NULL COMMENT '成交额',
            `circulating_market_value` decimal(15,2) DEFAULT NULL COMMENT '流通市值',
            `total_market_value` decimal(15,2) DEFAULT NULL COMMENT '总市值',
            `turnover` decimal(10,2) DEFAULT NULL COMMENT '换手率',
            `sealing_fund` decimal(15,2) DEFAULT NULL COMMENT '封板资金',
            `first_sealing_time` varchar(6) DEFAULT NULL COMMENT '首次封板时间',
            `last_sealing_time` varchar(6) DEFAULT NULL COMMENT '最后封板时间',
            `explosion_count` int DEFAULT NULL COMMENT '炸板次数',
            `limit_up_stats` varchar(20) DEFAULT NULL COMMENT '涨停统计',
            `continuous_boards` int DEFAULT NULL COMMENT '连板数',
            `industry_eastmoney` varchar(50) DEFAULT NULL COMMENT '所属行业_东财',
            `date` date NOT NULL COMMENT '日期',
            PRIMARY KEY (`id`),
            KEY `idx_stock_code_date` (`stock_code`, `date`),
            KEY `idx_date` (`date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票每日涨停板数据'
        """
        
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
        
       #  # 6. 删除当天的旧数据（如果存在）
       #  delete_sql = "DELETE FROM stock_daily_ztb WHERE date = %s"
       #  with engine.connect() as conn:
       #      result = conn.execute(delete_sql, (stock_zt_pool_em_df['date'].iloc[0],))
       #      if result.rowcount > 0:
       #          print(f"删除了 {result.rowcount} 条当天的旧数据")
        
        # 7. 插入新数据
        stock_zt_pool_em_df.to_sql('stock_daily_ztb', engine, if_exists='append', index=False)
        message = f"成功插入 {len(stock_zt_pool_em_df)} 条数据到 stock_daily_ztb 表"
        print(message)
        
        # 关闭数据库连接
        engine.dispose()
        
        return message
        
    except Exception as e:
        print(f"更新涨停板数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    
    # update_industry_flow_data()  # 更新行业板块资金流向数据 industry_flow_ODS 
    # update_stock_flow()  # 更新股票资金流数据 stock _daily_flow
    # update_stock_ztb_data()  # 更新股票涨停板数据 stock_daily_ztb

    # ###################
    update_stock_spot_data()  # 更新股票实时数据 stock_daily_qfq_new -> stock_daily_qfq

    # update_industry_ths_index_daily()  # 更新行业板块日数据 industry_ths_index

    



    #####################
    # update_all_industry_index_data(None)  # 更新所有行业指数数据 industry_ths_index_ODS

    print("finish")
