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

-- 创建行业风险表
CREATE TABLE IF NOT EXISTS industry_risks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    industry VARCHAR(50) NOT NULL,
    analyze_date DATE NOT NULL,
    risk_analysis TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_industry (industry),
    INDEX idx_analyze_date (analyze_date)
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
