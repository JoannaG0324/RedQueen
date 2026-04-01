# stock_db 数据库结构文档
> 适用于 AI 开发、系统构建、接口生成、模型理解使用

## 表：industry_flow_calc | 行业资金流向均线计算表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| date | date | YES |  | 交易日期 |
| industry_code | text | YES |  | 行业代码 |
| industry_name | text | YES |  | 行业名称 |
| net_inflow | double | YES |  | 当日净流入(亿元) |
| net_inflow_ma2 | double | YES |  | 2日净流入均值 |
| net_inflow_ma3 | double | YES |  | 3日净流入均值 |
| net_inflow_ma5 | double | YES |  | 5日净流入均值 |
| net_inflow_ma10 | text | YES |  | 10日净流入均值 |
| net_inflow_ma20 | text | YES |  | 20日净流入均值 |

---

## 表：industry_flow_ODS | 行业板块资金流向数据
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 自增序号 |
| serial_no | varchar(20) | YES |  | 序号/排名 |
| industry_name | varchar(50) | YES |  | 行业板块名称 |
| change_percent | decimal(10,2) | YES |  | 涨跌幅(%) |
| total_volume | decimal(15,2) | YES |  | 总成交量(万手) |
| total_amount | decimal(15,2) | YES |  | 总成交额(亿元) |
| net_inflow | decimal(15,2) | YES |  | 净流入(亿元) |
| up_count | int | YES |  | 上涨家数 |
| down_count | int | YES |  | 下跌家数 |
| avg_price | decimal(10,2) | YES |  | 均价(元) |
| top_stock_name | varchar(50) | YES |  | 领涨股名称 |
| top_stock_change | decimal(10,2) | YES |  | 领涨股涨跌幅(%) |
| date | date | YES |  | 日期 |

---

## 表：industry_ths | 同花顺行业分类表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 主键ID |
| industry_code | varchar(10) | NO |  | 行业代码 |
| industry_name | varchar(50) | NO |  | 行业名称 |
| edit_date | date | YES |  | 编辑日期 |
| flag | tinyint | YES |  | 标志位(1=有效) |

---

## 表：industry_ths_index | 同花顺行业指数行情表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 主键ID |
| industry_code | varchar(10) | NO |  | THS行业代码 |
| open | float | YES |  | 开盘价 |
| high | float | YES |  | 最高价 |
| low | float | YES |  | 最低价 |
| close | float | YES |  | 收盘价 |
| volume | float | YES |  | 成交量 |
| amount | float | YES |  | 成交额 |
| update_time | datetime | YES |  | 更新时间 |
| date | date | YES |  | 交易日期 |

---

## 表：industry_ths_index_calc | 行业指数技术指标计算表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  |  |
| industry_code | varchar(20) | YES |  | 行业代码 |
| date | date | YES |  | 交易日期 |
| ma3 | double | YES |  | 3日均线 |
| ma5 | double | YES |  | 5日均线 |
| ma10 | double | YES |  | 10日均线 |
| ma20 | double | YES |  | 20日均线 |
| ma30 | double | YES |  | 30日均线 |
| ma60 | double | YES |  | 60日均线 |
| ma90 | double | YES |  | 90日均线 |
| ma120 | double | YES |  | 120日均线 |
| ma200 | double | YES |  | 200日均线 |
| atr3 | double | YES |  | 3日平均真实波幅 |
| atr5 | double | YES |  | 5日平均真实波幅 |
| atr10 | double | YES |  | 10日平均真实波幅 |
| atr14 | double | YES |  | 14日平均真实波幅 |
| created_at | timestamp | YES | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamp | YES | CURRENT_TIMESTAMP | 更新时间 |

---

## 表：industry_ths_stock | 同花顺行业成分股对应表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| stock_code | text | YES |  | 股票代码 |
| stock_name | text | YES |  | 股票名称 |
| industry_code | text | YES |  | 行业代码 |
| edit_date | date | YES |  | 编辑日期 |

---

## 表：stock_daily_flow | 股票每日资金流向数据
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 自增主键 |
| serial_number | int | YES |  | 序号 |
| stock_code | varchar(10) | NO |  | 股票代码 |
| stock_name | varchar(50) | YES |  | 股票名称 |
| close | decimal(10,2) | YES |  | 最新价 |
| change_rate | decimal(10,4) | YES |  | 涨跌幅 |
| turnover | decimal(10,2) | YES |  | 换手率 |
| inflow_amount | varchar(50) | YES |  | 流入资金（原始） |
| outflow_amount | varchar(50) | YES |  | 流出资金（原始） |
| net_amount | varchar(50) | YES |  | 净额（原始） |
| total_amount | varchar(50) | YES |  | 成交额（原始） |
| inflow_amount_wan | decimal(15,2) | YES |  | 流入资金（万元） |
| outflow_amount_wan | decimal(15,2) | YES |  | 流出资金（万元） |
| net_amount_wan | decimal(15,2) | YES |  | 净额（万元） |
| total_amount_wan | decimal(15,2) | YES |  | 成交额（万元） |
| date | date | NO |  | 日期 |

---

## 表：stock_daily_qfq | 股票前复权日线行情表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 主键ID |
| stock_code | text | YES |  | 股票代码 |
| date | date | YES |  | 交易日期 |
| open | double | YES |  | 开盘价 |
| close | double | YES |  | 收盘价 |
| high | double | YES |  | 最高价 |
| low | double | YES |  | 最低价 |
| volume | double | YES |  | 成交量 |
| amount | double | YES |  | 成交额 |
| amplitude | double | YES |  | 振幅 |
| change_rate | double | YES |  | 涨跌幅 |
| change_amount | double | YES |  | 涨跌额 |
| turnover | double | YES |  | 换手率 |

---

## 表：stock_daily_qfq_calc | 股票技术指标计算表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 主键ID |
| stock_code | varchar(20) | YES |  | 股票代码 |
| date | date | YES |  | 交易日期 |
| ma3 | double | YES |  | 3日均线 |
| ma5 | double | YES |  | 5日均线 |
| ma10 | double | YES |  | 10日均线 |
| ma20 | double | YES |  | 20日均线 |
| ma30 | double | YES |  | 30日均线 |
| ma60 | double | YES |  | 60日均线 |
| ma90 | double | YES |  | 90日均线 |
| ma120 | double | YES |  | 120日均线 |
| ma200 | double | YES |  | 200日均线 |
| atr3 | double | YES |  | 3日ATR |
| atr5 | double | YES |  | 5日ATR |
| atr10 | double | YES |  | 10日ATR |
| atr14 | double | YES |  | 14日ATR |
| created_at | timestamp | YES |  | 创建时间 |
| updated_at | timestamp | YES |  | 更新时间 |
| growth_streak_days | decimal(5,1) | YES |  | 股价连涨天数 |
| growth_streak_pct | decimal(10,4) | YES |  | 股价连涨幅度 |

---

## 表：stock_daily_qfq_new | 股票新版前复权日线（扩展字段）
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | bigint | YES |  | 主键ID |
| stock_code | text | YES |  | 股票代码 |
| stock_name | text | YES |  | 股票名称 |
| close | double | YES |  | 收盘价 |
| change_rate | double | YES |  | 涨跌幅 |
| change_amount | double | YES |  | 涨跌额 |
| volume | double | YES |  | 成交量 |
| amount | double | YES |  | 成交额 |
| amplitude | double | YES |  | 振幅 |
| high | double | YES |  | 最高价 |
| low | double | YES |  | 最低价 |
| open | double | YES |  | 开盘价 |
| pre_close | double | YES |  | 昨收价 |
| volume_ratio | double | YES |  | 量比 |
| turnover | double | YES |  | 换手率 |
| pe_dynamic | double | YES |  | 动态市盈率 |
| pb | double | YES |  | 市净率 |
| total_market_value | double | YES |  | 总市值 |
| circulating_market_value | double | YES |  | 流通市值 |
| change_speed | double | YES |  | 涨速 |
| 5_minute_change | double | YES |  | 5分钟涨幅 |
| 60_day_change_rate | double | YES |  | 60日涨幅 |
| year_change_rate | double | YES |  | 年涨幅 |
| date | date | YES |  | 交易日期 |

---

## 表：stock_daily_ztb | 股票每日涨停板数据
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| id | int | NO |  | 自增主键 |
| serial_number | int | YES |  | 序号 |
| stock_code | varchar(10) | NO |  | 股票代码 |
| stock_name | varchar(50) | YES |  | 股票名称 |
| change_rate | decimal(10,4) | YES |  | 涨跌幅 |
| close | decimal(10,2) | YES |  | 最新价 |
| amount | decimal(15,2) | YES |  | 成交额 |
| circulating_market_value | decimal(15,2) | YES |  | 流通市值 |
| total_market_value | decimal(15,2) | YES |  | 总市值 |
| turnover | decimal(10,2) | YES |  | 换手率 |
| sealing_fund | decimal(15,2) | YES |  | 封板资金 |
| first_sealing_time | varchar(6) | YES |  | 首次封板时间 |
| last_sealing_time | varchar(6) | YES |  | 最后封板时间 |
| explosion_count | int | YES |  | 炸板次数 |
| limit_up_stats | varchar(20) | YES |  | 涨停统计 |
| continuous_boards | int | YES |  | 连板数 |
| industry_eastmoney | varchar(50) | YES |  | 所属行业_东财 |
| date | date | NO |  | 日期 |

---

## 表：stock_info | 股票基础信息表
| 字段名 | 字段类型 | 是否允许为空 | 默认值 | 字段注释 |
|--------|----------|--------------|--------|----------|
| stock_code | text | YES |  | 股票代码 |
| stock_name | text | YES |  | 股票名称 |
| ipo_date | text | YES |  | 上市日期 |
| market | text | YES |  | 市场板块(主板/创业板/科创板) |