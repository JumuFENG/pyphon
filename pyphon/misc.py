import requests
import math

def join_url(srv, path):
    if srv.endswith('/') and path.startswith('/'):
        return srv + path[1:]
    elif srv.endswith('/') or path.startswith('/'):
        return srv + path
    return srv + '/' + path

def get_stock_snapshot(code):
    url = f'https://hsmarketwg.eastmoney.com/api/SHSZQuoteSnapshot?id={code}&callback=?'
    response = requests.get(url)
    snapshot = response.json()

    name = snapshot.get('name')
    topprice = safe_float(snapshot.get('topprice'))
    bottomprice = safe_float(snapshot.get('bottomprice'))
    realtimequote = snapshot.get('realtimequote', {})
    fivequote = snapshot.get('fivequote', {})

    latestPrice = safe_float(realtimequote.get('currentPrice'))
    date = realtimequote.get('date')
    zdf = realtimequote.get('zdf')
    openPrice = safe_float(fivequote.get('openPrice'))
    lastClose = safe_float(fivequote.get('yesClosePrice'))

    # 提取买卖盘
    buysells = {k: v for k, v in fivequote.items() if k.startswith('buy') or k.startswith('sale')}

    change = float(zdf.replace('%', '')) / 100 if zdf else None

    return {
        'code': code,
        'name': name,
        'price': latestPrice,
        'open': openPrice,
        'lclose': lastClose,
        'buysells': buysells,
        'change': change,
        'change_px': (latestPrice - lastClose) if latestPrice and lastClose else None,
        'top_price': topprice,
        'bottom_price': bottomprice
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
        if snap['sale1'] == snap['buy1']:
            ask5 = min(price * 1.03, top_price)
            bid5 = max(price * 0.97, bottom_price)
        return {'top_price': top_price, 'bottom_price': bottom_price, 'price': price, 'ask5': ask5, 'bid5': bid5}
    except Exception as e:
        logger.error('get_rt_price error %s', e)

def get_mkt_code(code):
    assert len(code) == 6, "stock code length should be 6"
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
