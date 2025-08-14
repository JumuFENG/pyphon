import requests
import math
import re
from datetime import datetime
from functools import lru_cache

def delay_seconds(daytime:str)->float:
    '''计算当前时间到daytime的时间间隔'''
    dnow = datetime.now()
    dtarr = daytime.split(':')
    hr = int(dtarr[0])
    minutes = 0 if len(dtarr) < 2 else int(dtarr[1])
    secs = 0 if len(dtarr) < 3 else int(dtarr[2])
    target_time = dnow.replace(hour=hr, minute=minutes, second=secs)
    return (target_time - dnow).total_seconds()

def join_url(srv, path):
    if srv.endswith('/') and path.startswith('/'):
        return srv + path[1:]
    elif srv.endswith('/') or path.startswith('/'):
        return srv + path
    return srv + '/' + path

def get_stock_snapshot(code):
    url = f'https://hsmarketwg.eastmoney.com/api/SHSZQuoteSnapshot?id={code}&callback=?'
    response = requests.get(url)
    response.raise_for_status()
    snapshot = response.json()

    realtimequote = snapshot.get('realtimequote', {})
    fivequote = snapshot.get('fivequote', {})
    buysells = {k: v for k, v in fivequote.items() if k.startswith('buy') or k.startswith('sale')}

    zdf = realtimequote.get('zdf')
    change = float(zdf.replace('%', '')) / 100 if zdf else None

    date = realtimequote.get('date')
    date = f'{date[:4]}-{date[4:6]}-{date[6:8]}'

    return {
        'code': code,
        'name': snapshot.get('name'),
        'price': safe_float(realtimequote.get('currentPrice')),
        'open': safe_float(realtimequote.get('open')),
        'high': safe_float(realtimequote.get('high')),
        'low': safe_float(realtimequote.get('low')),
        'lclose': safe_float(fivequote.get('yesClosePrice')),
        'buysells': buysells,
        'change': change,
        'change_px': safe_float(realtimequote.get('zd')),
        'top_price': safe_float(snapshot.get('topprice')),
        'bottom_price': safe_float(snapshot.get('bottomprice')),
        'date': date,
        'time': realtimequote.get('time')
    }

def safe_float(v):
    try:
        return float(v)
    except Exception as e:
        return .0

def get_rt_price(code):
    try:
        snap = get_stock_snapshot(code)
        top_price = snap['top_price']
        bottom_price = snap['bottom_price']
        price = snap['price']
        bid5 = safe_float(snap['buysells']['buy5'])
        ask5 = safe_float(snap['buysells']['sale5'])
        if snap['buysells']['sale1'] == snap['buysells']['buy1']:
            ask5 = min(price * 1.03, top_price)
            bid5 = max(price * 0.97, bottom_price)
        return {'top_price': top_price, 'bottom_price': bottom_price, 'price': price, 'ask5': ask5, 'bid5': bid5}
    except Exception as e:
        raise e

def get_mkt_code(code):
    assert len(code) == 6, f"stock code length should be 6 not {code}"
    bj_head = ("4", "8", "92")
    sh_head = ("5", "6", "7", "9", "110", "113", "118", "132", "204")
    if code.startswith(bj_head):
        return "BJ"
    elif code.startswith(sh_head):
        return "SH"
    return 'SZ'

def calc_buy_count(amount, price):
    ct = (amount / 100) / price
    if amount - price * math.floor(ct) * 100 > (price * math.ceil(ct) * 100 - amount):
        return 100 * math.ceil(ct)
    return 100 * math.floor(ct) if ct > 1 else 100

@lru_cache(maxsize=1)
def get_system_date():
    """
    从上交所获取系统日期信息
    """
    url = 'http://www.sse.com.cn/js/common/systemDate_global.js'
    response = requests.get(url, timeout=5)
    response.raise_for_status()

    js_content = response.text

    # 使用正则表达式提取JavaScript变量
    matchsd = re.search(r'var systemDate_global\s*=\s*"([^"]+)"', js_content)
    matchtd = re.search(r'var whetherTradeDate_global\s*=\s*(\w+)', js_content)
    matchlast = re.search(r'var lastTradeDate_global\s*=\s*"([^"]+)"', js_content)

    # 提取数据
    system_date = matchsd.group(1) if matchsd else None
    is_trade_day = matchtd.group(1) == 'true' if matchtd else False
    last_trade_date = matchlast.group(1) if matchlast else None

    return {
        'systemDate': system_date,
        'isTradeDay': is_trade_day,
        'lastTradeDate': last_trade_date
    }


def is_today_trading_day():
    """
    判断今天是否为交易日
    """
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    if now.weekday() >= 5:
        return False

    try:
        # 获取系统日期信息
        sysdate = get_system_date()
        # 检查今天是否为交易日
        return today == sysdate['systemDate'] and sysdate['isTradeDay']
    except Exception as e:
        return now.weekday() < 5
