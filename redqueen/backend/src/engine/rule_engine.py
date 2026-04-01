from typing import List, Dict, Any, Tuple
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed


class RuleEngine:
    """规则引擎模块"""
    
    def __init__(self):
        """初始化规则引擎"""
        pass
    
    def scan_stock(self, stock_code: str, stock_data: Dict[str, Any], enabled_rules: List[str] = None) -> Dict[str, Any]:
        """扫描单个股票"""
        results = {
            "stock_code": stock_code,
            "triggered_rules": [],
            "total_triggers": 0
        }
        
        # 执行规则
        rule_map = {
            "rule_ma_crossover": self.rule_ma_crossover,
            "rule_trendline_breakout": self.rule_trendline_breakout,
            "rule_dow_theory": self.rule_dow_theory,
            "rule_macd_divergence": self.rule_macd_divergence,
            "rule_bollinger_band_breakout": self.rule_bollinger_band_breakout,
            "rule_quantile_regression": self.rule_quantile_regression,
            "rule_volume_price_divergence": self.rule_volume_price_divergence,
            "rule_obv_trend": self.rule_obv_trend,
            "rule_capital_flow": self.rule_capital_flow,
            "rule_turnover_trend": self.rule_turnover_trend,
            "rule_atr_volatility": self.rule_atr_volatility,
            "rule_volatility_expansion": self.rule_volatility_expansion,
            "rule_amplitude_trend": self.rule_amplitude_trend
        }
        
        # 如果没有指定启用的规则，则执行所有规则
        if enabled_rules is None:
            enabled_rules = list(rule_map.keys())
        
        for rule_name in enabled_rules:
            if rule_name in rule_map:
                rule_func = rule_map[rule_name]
                try:
                    triggered, details = rule_func(stock_data)
                    if triggered:
                        results["triggered_rules"].append({
                            "rule_name": rule_name,
                            "details": details
                        })
                except Exception as e:
                    print(f"执行规则 {rule_name} 时出错: {e}")
        
        results["total_triggers"] = len(results["triggered_rules"])
        return results
    
    def batch_scan(self, stock_data_dict: Dict[str, Dict[str, Any]], max_workers: int = 4, enabled_rules: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """批量扫描股票"""
        results = {}
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_stock = {executor.submit(self.scan_stock, stock_code, stock_data, enabled_rules): stock_code 
                              for stock_code, stock_data in stock_data_dict.items()}
            
            # 收集结果
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                try:
                    results[stock_code] = future.result()
                except Exception as e:
                    print(f"扫描股票 {stock_code} 时出错: {e}")
                    results[stock_code] = {
                        "stock_code": stock_code,
                        "triggered_rules": [],
                        "total_triggers": 0,
                        "error": str(e)
                    }
        
        return results
    
    def rule_ma_crossover(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """均线交叉趋势异动"""
        close = np.array(data["close"])
        volume = np.array(data["volume"])
        
        # 计算均线
        ma5 = self._calculate_ma(close, 5)
        ma20 = self._calculate_ma(close, 20)
        vol_ma20 = self._calculate_ma(volume, 20)
        
        # 检查金叉
        if len(ma5) < 2 or len(ma20) < 2:
            return False, {}
        
        # 金叉信号：MA5上穿MA20
        golden_cross = ma5[-1] > ma20[-1] and ma5[-2] <= ma20[-2]
        
        # 量能确认
        volume_confirm = volume[-1] >= 1.2 * vol_ma20[-1]
        
        # 连续2日收盘价大于MA20
        price_confirm = all(close[-i] > ma20[-i] for i in range(1, 3))
        
        if golden_cross and volume_confirm and price_confirm:
            return True, {
                "ma5": float(ma5[-1]),
                "ma20": float(ma20[-1]),
                "volume": float(volume[-1]),
                "vol_ma20": float(vol_ma20[-1])
            }
        
        return False, {}
    
    def rule_trendline_breakout(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """趋势线突破异动"""
        low = np.array(data["low"])
        close = np.array(data["close"])
        
        # 取最近30日低点拟合上升趋势线
        if len(low) < 30:
            return False, {}
        
        # 简单线性回归拟合
        x = np.arange(len(low[-30:]))
        y = low[-30:]
        slope, intercept = np.polyfit(x, y, 1)
        
        # 计算趋势线价格
        trendline_price = slope * (len(low) - 1) + intercept
        
        # 突破幅度1%
        breakout_threshold = trendline_price * 1.01
        
        # 检查收盘价是否突破
        if close[-1] > breakout_threshold:
            # 连续2日不跌破趋势线
            if len(close) >= 20:
                trendline_prices = slope * np.arange(len(low)-19, len(low)) + intercept
                # 确保长度匹配
                if len(trendline_prices) == len(close[-20:]):
                    above_trendline = all(close[-20:] > trendline_prices)
                else:
                    # 取最近的N个点，确保长度匹配
                    min_length = min(len(trendline_prices), len(close[-20:]))
                    above_trendline = all(close[-min_length:] > trendline_prices[-min_length:])
            else:
                above_trendline = False
            
            if above_trendline:
                return True, {
                    "slope": float(slope),
                    "breakout_price": float(close[-1]),
                    "trendline_price": float(trendline_price)
                }
        
        return False, {}
    
    def rule_dow_theory(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """道氏高低点趋势异动"""
        high = np.array(data["high"])
        low = np.array(data["low"])
        
        if len(high) < 60:
            return False, {}
        
        # 识别高低点
        highs = self._identify_extrema(high, 10, True)
        lows = self._identify_extrema(low, 10, False)
        
        if len(highs) < 2 or len(lows) < 2:
            return False, {}
        
        # 检查更高低点和更高高点
        higher_low = lows[-1] > lows[-2]
        higher_high = highs[-1] > highs[-2]
        
        if higher_low and higher_high:
            return True, {
                "high1": float(highs[-2]),
                "high2": float(highs[-1]),
                "low1": float(lows[-2]),
                "low2": float(lows[-1])
            }
        
        return False, {}
    
    def rule_macd_divergence(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """MACD趋势背离异动"""
        close = np.array(data["close"])
        
        if len(close) < 60:
            return False, {}
        
        # 计算MACD
        ema12 = self._calculate_ema(close, 12)
        ema26 = self._calculate_ema(close, 26)
        dif = ema12 - ema26
        dea = self._calculate_ema(dif, 9)
        
        if len(dif) < 30:
            return False, {}
        
        # 检查底背离
        price_low = np.min(close[-30:])
        price_low_idx = np.argmin(close[-30:]) + len(close) - 30
        dif_low = np.min(dif[price_low_idx-10:price_low_idx+1])
        
        # 最近价格创新低，但DIF未创新低
        recent_low = close[-1]
        recent_dif = dif[-1]
        
        divergence = recent_low <= price_low and recent_dif > dif_low
        
        # 金叉信号
        golden_cross = dif[-1] > dea[-1] and dif[-2] <= dea[-2]
        
        if divergence and golden_cross:
            return True, {
                "dif": float(dif[-1]),
                "dea": float(dea[-1]),
                "price_low": float(price_low),
                "recent_low": float(recent_low)
            }
        
        return False, {}
    
    def rule_bollinger_band_breakout(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """布林带通道突破异动"""
        close = np.array(data["close"])
        
        if len(close) < 40:
            return False, {}
        
        # 计算布林带
        ma20 = self._calculate_ma(close, 20)
        std20 = self._calculate_std(close, 20)
        upper_band = ma20 + 2 * std20
        lower_band = ma20 - 2 * std20
        
        # 计算带宽
        bandwidth = (upper_band - lower_band) / ma20
        
        if len(bandwidth) < 2:
            return False, {}
        
        # 带宽收敛（低于20%分位）
        bandwidth_quantile = np.percentile(bandwidth[-60:], 20)
        convergence = bandwidth[-1] <= bandwidth_quantile
        
        # 向上突破
        breakout = close[-1] > upper_band[-1]
        
        # 持续2日
        if len(close) >= 2 and len(upper_band) >= 2:
            breakout_confirm = close[-1] > upper_band[-1] and close[-2] > upper_band[-2]
        else:
            breakout_confirm = False
        
        if convergence and breakout_confirm:
            return True, {
                "close": float(close[-1]),
                "upper_band": float(upper_band[-1]),
                "bandwidth": float(bandwidth[-1])
            }
        
        return False, {}
    
    def rule_quantile_regression(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """分位数回归趋势异动"""
        close = np.array(data["close"])
        
        if len(close) < 120:
            return False, {}
        
        # 计算收益率
        returns = np.log(close[1:] / close[:-1])
        
        if len(returns) < 60:
            return False, {}
        
        # 简单线性回归（模拟分位数回归）
        x = np.arange(len(returns[-60:]))
        y = returns[-60:]
        slope, intercept = np.polyfit(x, y, 1)
        
        # 检查斜率由负变正
        if len(returns) >= 120:
            x_prev = np.arange(len(returns[-120:-60]))
            y_prev = returns[-120:-60]
            slope_prev, _ = np.polyfit(x_prev, y_prev, 1)
            
            if slope_prev < 0 and slope > 0 and (slope - slope_prev) > 0.001:
                return True, {
                    "slope": float(slope),
                    "slope_prev": float(slope_prev)
                }
        
        return False, {}
    
    def rule_volume_price_divergence(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """量价背离趋势异动"""
        close = np.array(data["close"])
        volume = np.array(data["volume"])
        
        if len(close) < 30:
            return False, {}
        
        # 识别最近两个低点
        lows = self._identify_extrema(close, 10, False)
        
        if len(lows) < 2:
            return False, {}
        
        # 价格创新低，成交量未创新低
        price_low1 = lows[-2]
        price_low2 = lows[-1]
        
        # 找到对应成交量
        volume_low1 = volume[np.argmin(close[-60:][:len(close[-60:])//2])]
        volume_low2 = volume[np.argmin(close[-60:][len(close[-60:])//2:]) + len(close[-60:])//2]
        
        # 底背离：价格新低，成交量未新低
        divergence = price_low2 < price_low1 and volume_low2 >= volume_low1 * 0.7
        
        # 3日内收阳
        if divergence:
            recent_returns = (close[-3:] - close[-4:-1]) / close[-4:-1]
            if any(recent_returns > 0):
                return True, {
                    "price_low1": float(price_low1),
                    "price_low2": float(price_low2),
                    "volume_low1": float(volume_low1),
                    "volume_low2": float(volume_low2)
                }
        
        return False, {}
    
    def rule_obv_trend(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """OBV能量潮趋势异动"""
        close = np.array(data["close"])
        volume = np.array(data["volume"])
        
        if len(close) < 60:
            return False, {}
        
        # 计算OBV
        obv = np.zeros(len(close))
        obv[0] = volume[0]
        
        for i in range(1, len(close)):
            if close[i] > close[i-1]:
                obv[i] = obv[i-1] + volume[i]
            elif close[i] < close[i-1]:
                obv[i] = obv[i-1] - volume[i]
            else:
                obv[i] = obv[i-1]
        
        # 计算OBV均线
        obv_ma20 = self._calculate_ma(obv, 20)
        
        # OBV创新高
        obv_high = np.max(obv[-60:])
        obv_high_idx = np.argmax(obv[-60:]) + len(obv) - 60
        
        # 价格未创新高
        price_high = np.max(close[-60:])
        price_high_idx = np.argmax(close[-60:]) + len(close) - 60
        
        divergence = obv_high_idx == len(obv) - 1 and price_high_idx != len(close) - 1
        
        # OBV上穿OBV均线
        if len(obv_ma20) >= 2:
            obv_cross = obv[-1] > obv_ma20[-1] and obv[-2] <= obv_ma20[-2]
        else:
            obv_cross = False
        
        if divergence and obv_cross:
            return True, {
                "obv": float(obv[-1]),
                "obv_ma20": float(obv_ma20[-1]),
                "obv_high": float(obv_high),
                "price_high": float(price_high)
            }
        
        return False, {}
    
    def rule_capital_flow(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """主力资金流趋势异动"""
        net_amount = np.array(data["net_amount_wan"])
        total_amount = np.array(data["total_amount_wan"])
        
        if len(net_amount) < 30:
            return False, {}
        
        # 计算5日累计净流入
        net_5d = np.sum(net_amount[-5:])
        total_5d = np.sum(total_amount[-5:])
        
        if total_5d == 0:
            return False, {}
        
        # 净流入占比≥5%
        ratio = net_5d / total_5d
        
        # 连续3日资金为正
        positive_days = sum(1 for x in net_amount[-3:] if x > 0)
        
        if ratio >= 0.05 and positive_days >= 3:
            return True, {
                "net_5d": float(net_5d),
                "total_5d": float(total_5d),
                "ratio": float(ratio),
                "positive_days": positive_days
            }
        
        return False, {}
    
    def rule_turnover_trend(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """换手率趋势异动"""
        turnover = np.array(data["turnover"])
        close = np.array(data["close"])
        
        if len(turnover) < 60:
            return False, {}
        
        # 计算20日换手率均值
        turnover_ma20 = self._calculate_ma(turnover, 20)
        
        # 当日换手率≥2倍均值
        if len(turnover_ma20) >= 1:
            turnover_ratio = turnover[-1] / turnover_ma20[-1]
        else:
            return False, {}
        
        # 股价处于相对低位
        price_percentile = np.percentile(close[-60:], 30)
        low_price = close[-1] <= price_percentile
        
        # 当日收涨
        price_rise = close[-1] > close[-2]
        
        # 持续2日
        if len(turnover) >= 2:
            turnover_confirm = turnover[-1] > turnover_ma20[-1] * 2 and turnover[-2] > turnover_ma20[-2] * 2
        else:
            turnover_confirm = False
        
        if turnover_ratio >= 2 and low_price and price_rise and turnover_confirm:
            return True, {
                "turnover": float(turnover[-1]),
                "turnover_ma20": float(turnover_ma20[-1]),
                "turnover_ratio": float(turnover_ratio)
            }
        
        return False, {}
    
    def rule_atr_volatility(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """ATR波动率异动"""
        atr14 = np.array(data["atr14"])
        close = np.array(data["close"])
        
        if len(atr14) < 30:
            return False, {}
        
        # ATR从10%历史分位上升幅度≥50%
        atr_percentile = np.percentile(atr14[-60:], 10)
        atr_rise = atr14[-1] >= atr_percentile * 1.5
        
        # 3日内收盘价持续上行
        if len(close) >= 3:
            price_rise = all(close[-i] > close[-(i+1)] for i in range(1, 4))
        else:
            price_rise = False
        
        if atr_rise and price_rise:
            return True, {
                "atr14": float(atr14[-1]),
                "atr_percentile": float(atr_percentile)
            }
        
        return False, {}
    
    def rule_volatility_expansion(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """波动率收敛-发散异动"""
        close = np.array(data["close"])
        
        if len(close) < 60:
            return False, {}
        
        # 计算20日收益率标准差
        returns = np.log(close[1:] / close[:-1])
        volatility = self._calculate_rolling_std(returns, 20)
        
        if len(volatility) < 20:
            return False, {}
        
        # 波动率降至历史20%分位并持续10日
        volatility_quantile = np.percentile(volatility[-60:], 20)
        low_volatility = all(v <= volatility_quantile for v in volatility[-10:])
        
        # 当日波动率≥2倍前值且收益率为正
        if len(volatility) >= 2 and len(returns) >= 1:
            volatility_expansion = volatility[-1] >= volatility[-2] * 2
            positive_return = returns[-1] > 0
        else:
            volatility_expansion = False
            positive_return = False
        
        if low_volatility and volatility_expansion and positive_return:
            return True, {
                "volatility": float(volatility[-1]),
                "volatility_prev": float(volatility[-2]),
                "return": float(returns[-1])
            }
        
        return False, {}
    
    def rule_amplitude_trend(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """振幅异动趋势识别"""
        amplitude = np.array(data["amplitude"])
        close = np.array(data["close"])
        
        if len(amplitude) < 30:
            return False, {}
        
        # 计算20日振幅均值
        amplitude_ma20 = self._calculate_ma(amplitude, 20)
        
        # 当日振幅≥1.5倍均值
        if len(amplitude_ma20) >= 1:
            amplitude_ratio = amplitude[-1] / amplitude_ma20[-1]
        else:
            return False, {}
        
        # 当日收涨
        price_rise = close[-1] > close[-2]
        
        # 持续2日
        if len(amplitude) >= 2:
            amplitude_confirm = amplitude[-1] > amplitude_ma20[-1] * 1.5 and amplitude[-2] > amplitude_ma20[-2] * 1.5
        else:
            amplitude_confirm = False
        
        if amplitude_ratio >= 1.5 and price_rise and amplitude_confirm:
            return True, {
                "amplitude": float(amplitude[-1]),
                "amplitude_ma20": float(amplitude_ma20[-1]),
                "amplitude_ratio": float(amplitude_ratio)
            }
        
        return False, {}
    
    def _calculate_ma(self, data: np.ndarray, window: int) -> np.ndarray:
        """计算移动平均"""
        return np.convolve(data, np.ones(window)/window, mode='valid')
    
    def _calculate_ema(self, data: np.ndarray, window: int) -> np.ndarray:
        """计算指数移动平均"""
        alpha = 2 / (window + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema
    
    def _calculate_std(self, data: np.ndarray, window: int) -> np.ndarray:
        """计算移动标准差"""
        return np.array([np.std(data[i-window:i]) for i in range(window, len(data)+1)])
    
    def _calculate_rolling_std(self, data: np.ndarray, window: int) -> np.ndarray:
        """计算滚动标准差"""
        result = []
        for i in range(window, len(data)+1):
            result.append(np.std(data[i-window:i]))
        return np.array(result)
    
    def _identify_extrema(self, data: np.ndarray, window: int, find_max: bool) -> List[float]:
        """识别极值点"""
        extrema = []
        for i in range(window, len(data)-window):
            window_data = data[i-window:i+window+1]
            if find_max:
                if data[i] == np.max(window_data):
                    extrema.append(data[i])
            else:
                if data[i] == np.min(window_data):
                    extrema.append(data[i])
        return extrema
