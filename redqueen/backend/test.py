import requests
import time
import random
import datetime

BASE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
UA_LIST = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

LOGIN_COOKIES = {
    "xqat": "44b6d0b96ffc3c7b2763cc95caa2adefac433dee",
    "xq_r_token": "15fef92c15d4e2bdadcd1ddd9ec5318d25606525",
    "xq_id_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOi0xLCJpc3MiOiJ1YyIsImV4cCI6MTc4MzY0NjYyNywiY3RtIjoxNzgxNTE3OTk1MjU4LCJjaWQiOiJkOWQwbjRBWnVwIn0.V5Yoq54rHHz9HX3eHwU1ejAnuR-0EwKAa75wfPMSNjIICbOOVArcGAS7VvvEz6uzCZR800VCvg-JKTKNdtg-p6kcJf1t-Xup1bq63ESRr-gpX__rjCUOG3dxMWKPJ33WXDRjWwctUoiMn_dcYQJMTLensyVrR_jdO7tCVfIAYMQ4jAvEJTWp33Qp9RVZzJQ3RLnLkI7REHij2rG5M2ewZMyfXKKn30KIcwQBxIpj24fnOUZhOP63oPEHjjfM8vfSXYUa6jNG2G9EEgeKA5M_76hl9fSiKeBJrEwzEEOW2e6MBEgaK8mmDhAyTG1jxEUYwolcVBENEJCQh2-ouL_MLw",
    "xq_a_token": "44b6d0b96ffc3c7b2763cc95caa2adefac433dee",
    "u": "351768282036827",
    "ssxmod_itna2": "1-Yq_x0DniYGq8Qi7eitGRDwPx_xQqqiK0QD9DBP01FkDux4jKidqDUYbT0D8bDCqqxDcQiexbmR20eqqIDDporK48fyGGDFgx4jeeo_xD/Ir4kQr7Vt9LOn_ijIGgjXHv1FSx228Y=ClZh0sRhvYWjIOREFsZoPxhoHsxOi7QIFNh1a88rb7QixFQmIYOFbHnPemI3fYS1D8pobfZmPA6SO6wKKoAr5Cxh9Dga3s/PIYZnpUjPw_mKEF546jhpawmtGmS8oxKaO2q=I0tNIAm5qAHHz2chW8qhcD3GEpYN9ipPq4ZYyrqB3rQTRWqPSTuUW7AGA_PIeWwS4qYpxaWftBxpR8QBDEWueaQAq5dw_0Whbuwn5F9BU_H3MFvnHRtw_nTuDauCq5HGOjcd6gD5W2iiitWQeaw/TxQw0jvpYxp/yIjHimTPbqp4bOKijAnHtaAnS8iT=Tud=b_jP5d_byS7S3Oj8k=7b2BkkK1tOakFwRE5NDOHw5OP5wofKqHUBGSuYPHGGMQR4HAdnY2qimCenyWePAEswCOPIvHub1jtyM8Dp_BYWOMOeoLzo4eIF1CiKB1P5frM73qLu4q=QF71RSIo=lhu4rYcWygDMnqeASbf/CqCY/QCw7UTD6v03epjEOd_vbnzgxoj4NSqpEqqQyg1aVe888NF9l2WCi_YvWl4SmsZhl=DDrHi4relcPZiDtG5Da74=2q84WhNDeqrrlo654BG8AYePlGDD",
    "ssxmod_itna": "1-Yq_x0DniYGq8Qi7eitGRDwPx_xQqqiK0QD9DBP01FkDux4jKidqDUYbT0D8bDCqqxDcQiexbmR20eqqlD0viTDnqD82DQeDvQPLrTwZQeWYxAqSrhDN3qQDP_M3oC34hYSyODp1CBMvsGYWBmksO4D=PxKDmeDUxD1FDDklneDxpPD5xDTDWeDGDD3F4DCm3EPD0Rv7RoA582wrYgvDYpP=4_PDY5XDAqLI_Sv5_0fDWawji8KDmF5=kxYs4GalRbuDlFwDm_TOI19DC90t_x=_FSEF06oqGGTXkbTqAWiiaeqWlioYBzt_ieKGeWD4UqxqgQQADvi==ghIDDiaocemgO4PC40=URcAu6ey1547eABmziYTY_zQDbYKb0Dn74dSqGQmlrxKBDObx3i4ejRhC2xixTBtqQA_DvKjXTFrzCr_Kq5tNxD",
    "smidV2": "20260113132717129c955cec7d3b89d7d459e2fc99f00c0048a20bc652aec80",
    "s": "c111wtfnmz",
    "device_id": "a15c0de44abe4a6f525b22feec464d6c",
    "cookiesu": "351768282036827",
    "acw_tc": "276077c217815219906723076e4afcc2bcc8ebedbaaa2e653e53dba7375dd3"
}

def get_random_ua():
    return random.choice(UA_LIST)

def ts_ms_to_date(ms_ts):
    sec = ms_ts / 1000
    dt = datetime.datetime.fromtimestamp(sec, tz=datetime.timezone(datetime.timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d")

def fetch_xueqiu_daily(symbol="SZ300655", bar_count=120, retry=2):
    session = requests.Session()
    session.cookies.update(LOGIN_COOKIES)

    headers = {
        "User-Agent": get_random_ua(),
        "Referer": f"https://xueqiu.com/{symbol}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty"
    }

    now_ms = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "period": "day",
        "type": "before",
        "begin": now_ms,
        "count": -bar_count,
        "indicator": "kline"
    }

    for attempt in range(retry + 1):
        sleep_sec = random.uniform(1.2, 2.2)
        time.sleep(sleep_sec)
        try:
            resp = session.get(
                url=BASE_URL,
                headers=headers,
                params=params,
                timeout=12
            )
            if resp.status_code != 200:
                print(f"[{symbol}] HTTP状态码异常: {resp.status_code}")
                print("原始返回文本:", resp.text[:800])
                continue

            json_data = resp.json()
            # 打印完整返回，排查结构
            print(f"[{symbol}] 完整返回json: {json_data}")

            if json_data.get("error_code") != 0:
                err_code = json_data.get("error_code")
                err_msg = json_data.get("error_description")
                print(f"[{symbol}] 接口错误码:{err_code}, 提示:{err_msg}")
                if err_code == 400016:
                    print("===== 警告：Cookie已过期，重新浏览器获取 =====")
                continue

            # 多层安全判断，防止key不存在
            data = json_data.get("data")
            if not data:
                print(f"[{symbol}] data字段为空")
                continue
            kline_raw = data.get("kline")
            if not isinstance(kline_raw, list):
                print(f"[{symbol}] kline不是数组，无行情数据")
                continue

            stock_name = data.get("name", "")
            result = []
            for item in kline_raw:
                result.append({
                    "symbol": symbol,
                    "stock_name": stock_name,
                    "date": ts_ms_to_date(item[0]),
                    "open": item[1],
                    "high": item[2],
                    "low": item[3],
                    "close": item[4],
                    "volume_hand": item[5],
                    "amount_yuan": item[6],
                    "change_pct": item[7]
                })
            print(f"[{symbol} {stock_name}] 抓取成功，共{len(result)}条日线数据")
            return result

        except requests.exceptions.RequestException as e:
            print(f"[{symbol}] 网络请求异常：{str(e)}，重试 {attempt+1}/{retry+1}")
        except KeyError as ke:
            print(f"[{symbol}] 字典键缺失异常: {str(ke)}")
        except Exception as e:
            print(f"[{symbol}] 未知程序异常：{str(e)}")

    print(f"[{symbol}] 全部重试次数耗尽，抓取失败")
    return None

if __name__ == "__main__":
    daily_data = fetch_xueqiu_daily(symbol="SZ300655", bar_count=120)
    if daily_data:
        print("\n========== 前5条日线数据 ==========")
        for row in daily_data[:5]:
            print(row)