-- 创建异动个股表
CREATE TABLE IF NOT EXISTS anomaly_stocks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50) NOT NULL,
    scan_date DATE NOT NULL,
    total_triggers INT NOT NULL,
    triggered_rules JSON NOT NULL,
    industry VARCHAR(50),
    industry_code VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_stock_code (stock_code),
    INDEX idx_scan_date (scan_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建扫描任务表
CREATE TABLE IF NOT EXISTS scan_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(50) NOT NULL UNIQUE,
    status ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED') DEFAULT 'PENDING',
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL,
    total_stocks INT DEFAULT 0,
    processed_stocks INT DEFAULT 0,
    error_message TEXT,
    INDEX idx_task_id (task_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 创建概念板块数据表
CREATE TABLE IF NOT EXISTS concept_plate_data (
    id INT PRIMARY KEY AUTO_INCREMENT,
    concept_id VARCHAR(20) DEFAULT NULL COMMENT '概念id',
    concept_name VARCHAR(100) DEFAULT NULL COMMENT '概念板块名称',
    stock_count INT DEFAULT NULL COMMENT '概念个股数量',
    avg_price DECIMAL(10,2) DEFAULT NULL COMMENT '平均价格',
    avg_change_amount DECIMAL(10,2) DEFAULT NULL COMMENT '平均涨跌额',
    avg_change_ratio DECIMAL(10,2) DEFAULT NULL COMMENT '平均涨跌幅(%)',
    total_volume BIGINT DEFAULT NULL COMMENT '总手',
    total_amount BIGINT DEFAULT NULL COMMENT '总成交金额',
    top_stock_code VARCHAR(10) DEFAULT NULL COMMENT '领涨股代码(去除cn_前缀)',
    top_stock_name VARCHAR(50) DEFAULT NULL COMMENT '领涨股名称',
    top_stock_price DECIMAL(10,2) DEFAULT NULL COMMENT '领涨股当前价',
    top_stock_change_amount DECIMAL(10,2) DEFAULT NULL COMMENT '领涨股涨跌额',
    top_stock_change_ratio DECIMAL(10,2) DEFAULT NULL COMMENT '领涨股涨跌幅(%)',
    date DATE DEFAULT NULL COMMENT '交易日期',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_concept_name (concept_name),
    INDEX idx_top_stock_code (top_stock_code),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='概念板块数据(搜狐来源)';
