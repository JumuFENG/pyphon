import json
import requests
from traceback import format_exc
from datetime import datetime, timedelta
from misc import get_rt_price, join_url, get_mkt_code, calc_buy_count, delay_seconds
from lofig import logger


class Account():
    def __init__(self):
        self.keyword = None
        self.stocks = []
        self.fundcode = '511880'
        self.hacc = None
        self.pure_assets = 0.0
        self.available_money = 0.0
        self.trading_records = []
        self.today_deals = None
        self.buy_jylx = ''
        self.sell_jylx = ''

    def get_stock(self, code):
        return next((s for s in self.stocks if s['code'] == code), None)

    @property
    def hold_account(self):
        if self.hacc:
            return self.hacc
        return self

    @property
    def jysession(self):
        return accld.jywg.session if accld.jywg else None

    @property
    def wgdomain(self):
        return accld.jywg.jywg if accld.jywg else None

    @property
    def valkey(self):
        return accld.jywg.validate_key if accld.jywg else None

    @staticmethod
    def extend_buydetail(buydetail, exdetail):
        if not isinstance(buydetail, list):
            return 0
        if not isinstance(exdetail, list):
            return 0
        cnt = 0
        for bd in exdetail:
            exbd = next((x for x in buydetail if x['sid'] == bd['sid'] and x['date'] == bd['date'] and x['type'] == bd['type']), None)
            if exbd:
                continue
            buydetail.append(bd)
            cnt += 1
        return cnt

    def extend_stock_buydetail(self, code, exdetail):
        stock = self.get_stock(code)
        if not stock:
            self.add_watch_stock(code, {'buydetail': exdetail, 'buydetail_full': exdetail})
            return

        if 'buydetail_full' not in stock:
            stock['buydetail_full'] = []
        ecnt = self.extend_buydetail(stock['buydetail_full'], exdetail)
        if ecnt == 0:
            return
        if 'buydetail' not in stock:
            stock['buydetail'] = []
        self.extend_buydetail(stock['buydetail'], exdetail)

    def load_watchings(self):
        if not accld.fha or not accld.fha.get('headers', None):
            logger.warning('loadWatchings no fha server configured')
            return

        wurl = join_url(accld.fha['server'], 'stock?act=watchings&acc=' + self.keyword)
        r = requests.get(wurl, headers=accld.fha['headers'])
        r.raise_for_status()
        watchings = r.json()
        if not watchings:
            logger.info('%s loadWatchings no watchings', self.keyword)
            return

        for code, stk in watchings.items():
            self.add_watch_stock(code[-6:], stk.get('strategies', None))

    def add_watch_stock(self, code, strgrp):
        stock = self.get_stock(code)
        if stock:
            osg = stock.get('strategies', None)
            if stock['holdCount'] == 0 or not osg:
                stock['strategies'] = strgrp
                if 'buydetail' in strgrp:
                    stock['buydetail'] = strgrp['buydetail']
                if 'buydetail_full' in strgrp:
                    stock['buydetail_full'] = strgrp['buydetail_full']
                return

            mxkeyid = 0
            exists_keys = []
            for k, v in osg['strategies'].items():
                if int(k) > mxkeyid:
                    mxkeyid = int(k)
                exists_keys.append(v['key'])
            for k, v in strgrp['strategies'].items():
                if v['key'] in exists_keys:
                    continue
                osg['strategies'][str(mxkeyid + 1)] = v
                mxkeyid += 1

            if stock['strategies']['amount'] != strgrp['amount']:
                stock['strategies']['amount'] = strgrp['amount']

            if 'buydetail' in strgrp:
                self.extend_buydetail(stock['buydetail'], strgrp['buydetail'])
            if 'buydetail_full' in strgrp:
                self.extend_buydetail(stock['buydetail_full'], strgrp['buydetail_full'])
            return

        count = sum([int(b['count']) for b in strgrp.get('buydetail', [])])
        self.stocks.append({
            'code': code, 'name': '', 'holdCount': count, 'availableCount': count,
            'strategies': strgrp, 'buydetail': strgrp.get('buydetail', []),
            'buydetail_full': strgrp.get('buydetail_full', [])
        })

    @property
    def order_url(self):
        pass

    def fetch_batches_deal_data(self, url, data):
        has_more_data = True
        orders = []

        try:
            while has_more_data:
                r = self.jysession.post(url, data=data)
                r.raise_for_status()
                deals = r.json()
                if deals['Status'] != 0:
                    logger.error('查询订单失败: %s', deals['Message'])
                    break
                if not deals['Data'] or len(deals['Data']) == 0:
                    logger.info('no orders found')
                    break
                orders.extend(deals['Data'])
                if 'Dwc' in deals['Data'][-1]:
                    data['dwc'] = deals['Data'][-1]['Dwc']
                if not deals['Data'][-1]['Dwc'] or len(deals['Data']) < int(data['qqhs']):
                    has_more_data = False
        except Exception as e:
            logger.error('查询订单失败: %s', str(e))
            logger.debug(format_exc())
        finally:
            return orders

    def get_orders(self):
        # 查询当日订单
        url = self.order_url
        data = {
            'qqhs': '20',
            'dwc': ''
        }
        return self.fetch_batches_deal_data(url, data)

    def tradeType_from_Mmsm(self, Mmsm):
        ignored = ['融券', ]
        if Mmsm in ignored:
            return

        sells = ['证券卖出', '担保品划出']
        if Mmsm in sells:
            return 'S'

        buys = ['证券买入', '担保品划入', '配售申购', '配股缴款', '网上认购']
        if Mmsm in buys:
            return 'B'

    @staticmethod
    def deals_to_buydetail(deals):
        return [
            {
                'code': deal['code'],
                'type': deal['tradeType'],
                'price': float(deal['price']),
                'count': int(deal['count']),
                'date': deal['time'],
                'sid': deal['sid']
            } for deal in deals
        ]

    @staticmethod
    def buydetails_to_deals(buydetails):
        return [
            {
                'code': buydetail['code'],
                'tradeType': buydetail['type'],
                'price': buydetail['price'],
                'count': buydetail['count'],
                'time': buydetail['date'],
                'sid': buydetail['sid']
            } for buydetail in buydetails
        ]

    def check_orders(self):
        data = self.get_orders()
        date = datetime.now().strftime('%Y-%m-%d')
        sdeals = {}
        for d in data:
            code = d.get('Zqdm', None)
            mmsm = d.get('Mmsm', None)
            status = d.get('Wtzt', None)
            bstype = self.tradeType_from_Mmsm(mmsm)
            if (status in ['已成', '已撤', '废单', '部撤'] or (status in ['部成'] and delay_seconds('15:00') < 0)) and bstype:
                count = int(d.get('Cjsl', 0))
                if count == 0:
                    logger.info('%s ignore deal %s %s', self.keyword, mmsm, d.get('Zqmc', ''))
                    continue
                if code not in sdeals:
                    sdeals[code] = []
                sdeals[code].append({
                    'code': code,
                    'price': float(d.get('Cjjg', 0)),
                    'count': count,
                    'sid': d.get('Wtbh', None),
                    'tradeType': bstype,
                    'time': date
                })
                record = next((x for x in self.trading_records if x['code'] == code and x['tradeType'] == bstype and x['sid'] == d.get('Wtbh', None)), None)
                if record:
                    self.trading_records.remove(record)
            elif status in ['已报'] and mmsm in ['配售申购']:
                logger.info('%s ignore deal %s %s', self.keyword, mmsm, d.get('Zqmc', ''))
                continue
            elif status in ['已报', '部成'] and bstype:
                logger.info('%s imcomplete deal %s %s %s', self.keyword, d.get('Zqmc', ''), status, mmsm)
                continue
            elif status in ['已确认'] and mmsm in ['担保品划入', '担保品划出']:
                accld.create_deals_for_transfer(d)
                continue
            else:
                logger.info('%s unknown deal type/status: %s', self.keyword, d)

        for code, deals in sdeals.items():
            self.extend_stock_buydetail(code, self.deals_to_buydetail(deals))

        return sdeals

    def archive_deals(self, codes):
        if not codes:
            return

        for c in codes:
            stk = self.get_stock(c)
            if stk:
                buydetail = stk.get('buydetail', [])
                buyrecs = sorted([c for c in buydetail if c['type'] == 'B'], key=lambda x: x['price'])
                sellrecs = [c for c in buydetail if c['type'] == 'S']
                scount = 0  # 初始化scount
                for rec in sellrecs:
                    cnt_matched = next((b for b in buyrecs if b['count'] == rec['count']), None)
                    if cnt_matched:
                        buyrecs.remove(cnt_matched)
                        continue
                    scount = rec['count']
                    for brec in buyrecs:
                        if brec['count'] > scount:
                            brec['count'] -= scount
                            scount = 0
                            break
                        scount -= brec['count']
                        brec['count'] = 0
                if scount > 0:
                    logger.error('sell count not archived %s %s', c, buydetail)
                    continue
                stk['buydetail'] = sorted([b for b in buyrecs if b['count'] > 0], key=lambda x: x['date'])
                stk['holdCount'] = sum([b['count'] for b in stk['buydetail']])
                stk['availableCount'] = stk['holdCount']

    def load_deals(self):
        # 查询当日订单，并将当日成交记录上传
        deals = self.check_orders()
        self.archive_deals(deals.keys())
        for c in deals:
            stk = self.get_stock(c)
            logger.debug('%s %s', c, deals[c])
            logger.debug(stk)

        updeals = []
        for c,d in deals.items():
            updeals.extend(d)
        self._upload_deals(updeals)

    def _upload_deals(self, deals, max_retry=3):
        if len(deals) == 0:
            return

        if not accld.fha or not accld.fha.get('headers', None):
            logger.warning('uploadDeals no fha server configured')
            return

        deals = [{
            **{k:v for k,v in d.items() if k != 'code'},
            'code': get_mkt_code(d['code']) + d['code'] if d['code'] else ''
        } for d in deals]

        url = join_url(accld.fha['server'], 'stock')
        data = {
            'act': 'deals',
            'acc': self.keyword,
            'data': json.dumps(deals)
        }
        logger.info('%s uploadDeals %s', self.keyword, deals)
        retry = 0
        while retry < max_retry:
            try:
                r = requests.post(url, headers=accld.fha['headers'], data=data)
                r.raise_for_status()
                if r.status_code == 200:
                    logger.info('%s uploadDeals success', self.keyword)
                    return
                else:
                    logger.error('%s uploadDeals failed: %s', self.keyword, r.text)
            except Exception as e:
                logger.error('%s uploadDeals error (try %d): %s', self.keyword, retry + 1, e)
                logger.debug(format_exc())
            retry += 1
        logger.error('%s uploadDeals failed after %d retries', self.keyword, max_retry)

    @property
    def datestr_fmt(self):
        return '%Y-%m-%d'

    @property
    def hisdeals_url(self):
        pass

    @property
    def hissxl_url(self):
        # 交割单查询 Stock Exchange List
        pass

    def get_history_deals(self, url, date):
        # 查询date至今所有订单
        datesections = []
        if isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')
        now = datetime.now()
        while True:
            edate = date + timedelta(days=89)
            datesections.append((date.strftime(self.datestr_fmt), min(edate, now).strftime(self.datestr_fmt)))
            if edate > now:
                break
            date = edate + timedelta(days=1)

        deals = []
        for st, et in datesections:
            data = {
                'st': st,
                'et': et,
                'qqhs': '20',
                'dwc': ''
            }

            deals.extend(self.fetch_batches_deal_data(url, data))

        return deals

    @staticmethod
    def get_deal_time(rq, sj):
        d = f'{rq[0:4]}-{rq[4:6]}-{rq[6:8]}'
        if len(sj) == 8:
            sj = sj[:6]
        if len(sj) != 6:
            return f'{d} 00:00'
        return f'{d} {sj[0:2]}:{sj[2:4]}:{sj[4:6]}'


    def load_his_deals(self, date):
        # 查询date至今所有历史订单(买卖订单)
        hdeals = self.get_history_deals(self.hisdeals_url, date)
        fetchedDeals = []
        for deali in hdeals:
            tradeType = self.tradeType_from_Mmsm(deali['Mmsm'])
            if not tradeType:
                logger.info('unknown trade type', deali['Mmsm'], deali)
                continue

            code = deali['Zqdm']
            if not code:
                continue

            dltime = self.get_deal_time(deali['Cjrq'], deali['Cjsj'])
            count = int(deali.get('Cjsl', 0))
            if count == 0:
                logger.info('invalid count %s', deali)
                continue

            fetchedDeals.append({
                'time': dltime, 'sid': deali.get('Wtbh', ''), 'code': code, 'tradeType': tradeType,
                'price': float(deali.get('Cjjg', 0)), 'count': count, 'fee': float(deali.get('Sxf', 0)),
                'feeYh': float(deali.get('Yhs', 0)), 'feeGh': float(deali.get('Ghf', 0))
            })

        self._upload_deals(fetchedDeals)

    def merge_cum_deals(self, deals):
        # 合并时间相同的融资利息
        tdeals = {}
        for d in deals:
            if d['time'] in tdeals:
                tdeals[d['time']]['price'] += d['price']
            else:
                tdeals[d['time']] = d

        return list(tdeals.values())

    def load_other_deals(self, date):
        # 查询date至今所有其它订单(非买卖订单)
        hdeals = self.get_history_deals(self.hissxl_url, date)
        fetchedDeals = []
        dealsTobeCum = []
        ignoredSm = ['融资买入', '融资借入', '偿还融资负债本金', '担保品卖出', '担保品买入', '担保物转入', '担保物转出', '融券回购', '融券购回', '证券卖出', '证券买入', '配股权证', '配股缴款']
        otherBuySm = ['红股入账', '配股入帐', '股份转入']
        otherSellSm = ['股份转出']
        otherSm = ['配售缴款', '新股入帐', '股息红利差异扣税', '偿还融资利息', '偿还融资逾期利息', '红利入账', '银行转证券', '证券转银行', '利息归本']
        fsjeSm = ['股息红利差异扣税', '偿还融资利息', '偿还融资逾期利息', '红利入账', '银行转证券', '证券转银行', '利息归本']
        deals_no_code = []
        for deali in hdeals:
            sm = deali.get('Ywsm', '')
            if sm in ignoredSm:
                continue

            tradeType = ''
            if sm in otherBuySm:
                tradeType = 'B'
            elif sm in otherSellSm:
                tradeType = 'S'
            elif sm in otherSm:
                logger.info('other tradeType %s', deali)
                tradeType = sm
                if sm == '股息红利差异扣税':
                    tradeType = '扣税'
                if sm in ('偿还融资利息', '偿还融资逾期利息'):
                    tradeType = '融资利息'
            else:
                logger.info('unknown deals %s, %s', sm, deali)
                continue

            code = deali.get('Zqdm', '')
            rq = deali['Fsrq'] if 'Fsrq' in deali and deali['Fsrq'] != '0' else deali['Ywrq']
            sj = deali['Fssj'] if 'Fssj' in deali and deali['Fssj'] != '0' else deali['Cjsj']
            dltime = self.get_deal_time(rq, sj)
            if sm == '红利入账' and dltime.endswith('0:0'):
                dltime = self.get_deal_time(deali['Fsrq'] if 'Fsrq' in deali and deali['Fsrq'] != '0' else deali['Ywrq'], '150000')

            count = int(deali.get('Cjsl', 0))
            price = float(deali.get('Cjjg', 0))
            if sm in fsjeSm:
                count = 1
                price = float(deali['Fsje'])

            sid = deali.get('Htbh', '')
            if sm == '配股入帐' and sid == '':
                continue

            drec = {
                    'time': dltime, 'sid': sid, 'code': code, 'tradeType': tradeType, 'price': price, 'count': count,
                    'fee': float(deali.get('Sxf', 0)), 'feeYh': float(deali.get('Yhs', 0)), 'feeGh': float(deali.get('Ghf', 0))
                }

            if not code:
                if count == 0:
                    drec['count'] = 1
                deals_no_code.append(drec)
                continue

            if tradeType == '融资利息':
                dealsTobeCum.append(drec)
            else:
                fetchedDeals.append(drec)

        if len(dealsTobeCum) > 0:
            ndeals = self.merge_cum_deals(dealsTobeCum)
            fetchedDeals.extend(ndeals)

        self._upload_deals(fetchedDeals)
        if len(deals_no_code) > 0:
            logger.info('deals no code: %s', deals_no_code)
            self._upload_deals(deals_no_code)

    def buy_fund_before_close(self):
        pass

    def get_assets_and_positions(self):
        pass

    def get_assets(self):
        pass

    def get_positions(self):
        pass

    def load_assets(self):
        s, p = self.get_assets_and_positions()
        self.on_assets_loaded(s)
        self.on_positions_loaded(p)

    def on_assets_loaded(self, assets):
        pass

    def parse_position(self, position):
        code = position.get('Zqdm')
        name = position.get('Zqmc')
        hold_count = int(position.get('Zqsl', 0))
        available_count = int(position.get('Kysl', 0))
        if hold_count - available_count != 0 and datetime.now().hour >= 15:
            available_count = hold_count
        hold_cost = float(position.get('Cbjg'))
        latest_price = float(position.get('Zxjg')) if 'Zxjg' in position else hold_cost
        return {
            'code': code,
            'name': name,
            'holdCount': hold_count,
            'holdCost': hold_cost,
            'availableCount': available_count,
            'latestPrice': latest_price
        }

    def on_positions_loaded(self, positions):
        if not positions:
            return
        for pos in positions:
            stocki = self.parse_position(pos)
            stock = self.get_stock(stocki['code'])
            if stock:
                stock.update(stocki)
            else:
                self.stocks.append(stocki)

    def get_count_form_data(self, code, price, tradeType):
        fd = {
            'stockCode': code,
            'price': price,
            'tradeType': tradeType,
        }
        mdic = {'SZ': 'SA', 'SH': 'HA', 'BJ': 'B'};
        fd['market'] = mdic[get_mkt_code(code)]
        fd['stockName'] = ''
        fd['gddm'] = ''
        return fd

    @property
    def count_url(self):
        pass

    def fetch_available_count(self, code, price, bstype):
        data = self.get_count_form_data(code, price, bstype)
        try:
            r = self.jysession.post(self.count_url, data=data)
            r.raise_for_status()
            robj = r.json()
            return int(robj['Data']['Kmml'])
        except Exception as e:
            return 0

    def get_form_data(self, code, price, count, tradeType):
        fd = {
            'stockCode': code,
            'price': price,
            'amount': count
        }
        mkt = get_mkt_code(code)
        if mkt == 'BJ':
            tradeType = '0' + tradeType
        fd['tradeType'] = tradeType
        mdic = { 'SZ': 'SA', 'SH': 'HA', 'BJ': 'B' };
        fd['market'] = mdic[mkt]
        return fd

    @property
    def trade_url(self):
        pass

    def trade(self, code, price, count, bstype):
        if bstype == 'B' and self.available_money < 1000:
            s = self.get_assets()
            self.on_assets_loaded(s)
            if self.available_money < 1000:
                logger.error('money not enough, available: %s', self.available_money)
                return

        if count < 1:
            logger.error(f'invalid count {count}')
            return

        if price == 0:
            rp = get_rt_price(code)
            price = rp['price']
            if bstype == 'B':
                price = rp['ask5'] if rp['ask5'] > 0 else rp['top_price']
            elif bstype == 'S':
                price = rp['bid5'] if rp['bid5'] > 0 else rp['bottom_price']

        final_count = count
        if count < 10:
            acount = self.fetch_available_count(code, price, bstype)
            if count > 0:
                final_count = 100 * (acount // 100 / count)
            if final_count < 100:
                logger.error('invalid count: %d, available count: %s, count: %s', final_count, acount, count)
                return

        data = self.get_form_data(code, price, final_count, bstype)
        try:
            r = self.jysession.post(self.trade_url, data=data)
            r.raise_for_status()
            robj = r.json()
            if robj['Status'] != 0 or len(robj['Data']) == 0:
                logger.error('submit trade error: %s, %s, %s', code, bstype, robj)
                return
            if bstype == 'B':
                self.available_money -= price * final_count
            elif bstype == 'S':
                self.available_money += price * final_count
            dltime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.hold_account.trading_records.append({
                'code': code, 'price': price, 'count': count, 'sid': robj['Data'][0]['Wtbh'], 'tradeType': bstype, 'time': dltime
            })
        except Exception as e:
            logger.error('submit trade error: %s, %s, %s', code, bstype, e)
            logger.debug(format_exc())


class NormalAccount(Account):
    def __init__(self):
        super().__init__()
        self.keyword = 'normal'

    @property
    def order_url(self):
        return join_url(self.wgdomain, f'Search/GetOrdersData?validatekey={self.valkey}')

    @property
    def hisdeals_url(self):
        return join_url(self.wgdomain, f'Search/GetHisDealData?validatekey={self.valkey}')

    @property
    def hissxl_url(self):
        return join_url(self.wgdomain, f'Search/GetFundsFlow?validatekey={self.valkey}')

    def get_assets_and_positions(self):
        url = join_url(self.wgdomain, f'/Com/queryAssetAndPositionV1?validatekey={self.valkey}')
        data = {
            'qqhs': '1000',
            'dwc': ''
        }
        try:
            r = self.jysession.post(url, data=data)
            r.raise_for_status()
            ap = r.json()
            if ap['Status'] != 0:
                logger.error('查询失败：%s', ap['Message'])
                return None, None
            assets = {k:v for k,v in ap['Data'][0].items() if k != 'positions'}
            return assets, ap['Data'][0]['positions']
        except Exception as e:
            logger.error(r.text)
            logger.error(e)
            logger.debug(format_exc())
            return None, None

    def get_assets(self):
        return self.get_assets_and_positions()[0]

    def on_assets_loaded(self, assets):
        if assets:
            self.pure_assets = float(assets['Zzc'])
            self.available_money = float(assets['Kyzj'])

    def get_positions(self):
        return self.get_assets_and_positions()[1]

    def get_count_form_data(self, code, price, tradeType):
        return super().get_count_form_data(code, price, tradeType)

    @property
    def count_url(self):
        return join_url(self.wgdomain, f'Trade/GetAllNeedTradeInfo?validatekey={self.valkey}')

    def get_form_data(self, code, price, count, tradeType):
        fd = super().get_form_data(code, price, count, tradeType)
        fd['zqmc'] = ''
        return fd

    @property
    def trade_url(self):
        return join_url(self.wgdomain, f'Trade/SubmitTradeV2?validatekey={self.valkey}')

    def buy_fund_before_close(self):
        accld.buy_bond_repurchase('204001')


class CollateralAccount(Account):
    def __init__(self):
        super().__init__()
        self.keyword = 'collat'
        self.buy_jylx = '6'
        self.sell_jylx = '7'

    @property
    def order_url(self):
        return join_url(self.wgdomain, f'MarginSearch/GetOrdersData?validatekey={self.valkey}')

    @property
    def datestr_fmt(self):
        return '%Y%m%d'

    @property
    def hisdeals_url(self):
        return join_url(self.wgdomain, f'MarginSearch/queryCreditHisMatchV2?validatekey={self.valkey}')

    @property
    def hissxl_url(self):
        return join_url(self.wgdomain, f'MarginSearch/queryCreditLogAssetV2?validatekey={self.valkey}')

    def get_assets_and_positions(self):
        return self.get_assets(), self.get_positions()

    def get_assets(self):
        jywg = accld.jywg
        if not jywg or not jywg.validate_key:
            return None

        url = join_url(self.wgdomain, f'/MarginSearch/GetRzrqAssets?validatekey={self.valkey}')
        data = {
            'hblx': 'RMB'
        }
        try:
            r = self.jysession.post(url, data=data)
            r.raise_for_status()
            a = r.json()
            return a['Data']
        except Exception as e:
            logger.error(r.text)
            logger.error(e)
            logger.debug(format_exc())
            return None

    def on_assets_loaded(self, assets):
        if not assets:
            return
        self.pure_assets = float(assets['Zzc']) - float(assets['Zfz'])
        self.available_money = float(assets['Zjkys'])
        if accld.credit_account:
            accld.credit_account.available_money = float(assets['Bzjkys'])

    def get_positions(self):
        url = join_url(self.wgdomain, f'/MarginSearch/GetStockList?validatekey={self.valkey}')
        try:
            r = self.jysession.post(url)
            r.raise_for_status()
            a = r.json()
            return a['Data']
        except Exception as e:
            logger.error(r.text)
            logger.error(e)
            logger.debug(format_exc())
            return None

    def get_count_form_data(self, code, price, tradeType):
        fd = super().get_count_form_data(code, price, tradeType)
        fd['xyjylx'] = self.buy_jylx if tradeType == 'B' else self.sell_jylx
        fd['stockName'] = ''
        fd['moneyType'] = 'RMB'
        return fd

    @property
    def count_url(self):
        return join_url(self.wgdomain, f'MarginTrade/GetKyzjAndKml?validatekey={self.valkey}')

    def get_form_data(self, code, price, count, tradeType):
        fd = super().get_form_data(code, price, count, tradeType)
        fd['stockName'] = ''
        fd['xyjylx'] = self.buy_jylx if tradeType == 'B' else self.sell_jylx
        return fd

    @property
    def trade_url(self):
        return join_url(self.wgdomain, f'MarginTrade/SubmitTradeV2?validatekey={self.valkey}')

    def buy_fund_before_close(self):
        accld.repay_margin_loan()
        self.trade(self.fundcode, 0, 1, 'B')


class CreditAccount(CollateralAccount):
    def __init__(self):
        super().__init__()
        self.keyword = 'credit'
        self.buy_jylx = 'a'
        self.sell_jylx = 'A'

    def buy_fund_before_close(self):
        pass

    def load_deals(self):
        pass

    def load_other_deals(self):
        pass

    def load_his_deals(self):
        pass

    def load_assets(self):
        pass

    def load_watchings(self):
        pass

    def get_orders(self):
        pass


class TrackingAccount(Account):
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
        self.available_money = 1e10
        self.sid = (int(datetime.now().strftime('%Y%m%d')) % 1000000) * 1000

    def load_his_deals(self, date):
        pass

    def load_other_deals(self, date):
        pass

    def check_orders(self):
        sdeals = {}
        for d in self.trading_records:
            code = d.get('code', None)
            if not code:
                continue
            if code not in sdeals:
                sdeals[code] = []
            sdeals[code].append({**{k: v for k,v in d.items()}})

        for code, deals in sdeals.items():
            self.extend_stock_buydetail(code, self.deals_to_buydetail(deals))

        return sdeals

    def trade(self, code, price, count, bstype):
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        stk = self.get_stock(code)
        if not stk:
            if bstype == 'S':
                logger.error('sell stock not found: %s %s', self.keyword, code)
                return
            self.add_watch_stock(code, {})
            stk = self.get_stock(code)

        rec = next((x for x in self.trading_records if x['code'] == code and x['tradeType'] == bstype and x['price'] == price and x['count'] == count), None)
        if rec:
            logger.error('duplicate trade record: %s %s %s %s %s', self.keyword, code, bstype, price, count)
            return

        if bstype == 'S':
            if stk['holdCount'] < count:
                logger.error('%s sell count more than hold count: %s', self.keyword, code)
                return
            stk['holdCount'] -= count
        else:
            stk['holdCount'] += count

        self.trading_records.append({
            'code': code,
            'price': price,
            'count': count,
            'time': time,
            'sid': self.sid,
            'tradeType': bstype,
        })
        self.sid += 1


class accld:
    jywg = None
    fha = None
    enable_credit = False
    normal_account = None
    collateral_account = None
    credit_account = None
    all_accounts = {}
    track_accounts = []

    @classmethod
    def load_accounts(self):
        self.normal_account = NormalAccount()
        self.all_accounts[self.normal_account.keyword] = self.normal_account
        self.normal_account.load_watchings()
        if self.enable_credit:
            self.collateral_account = CollateralAccount()
            self.collateral_account.load_watchings()
            self.credit_account = CreditAccount()
            self.credit_account.hacc = self.collateral_account
            self.all_accounts[self.collateral_account.keyword] = self.collateral_account
            self.all_accounts[self.credit_account.keyword] = self.credit_account

    @classmethod
    def init_track_accounts(self):
        if not self.fha or not self.fha.get('headers', None):
            logger.warning('fha not fully configured')
            return

        url = join_url(self.fha['server'], 'userbind?onlystock=1')
        r = requests.get(url, headers=self.fha['headers'])
        r.raise_for_status()
        accs = r.json()
        for acc in accs:
            if acc['realcash']:
                logger.info('skip realcash acc in track account')
                continue
            name = acc['name'] if 'name' in acc else acc['username'].split('.')[1]
            self.track_accounts.append(TrackingAccount(name))
        for account in self.track_accounts:
            self.all_accounts[account.keyword] = account
            account.load_watchings()

    @classmethod
    def upload_every_monday(self):
        """每周一上传历史成交记录"""
        now = datetime.now()
        # if now.weekday() != 0:
        #     return

        today = now.strftime('%Y-%m-%d')
        url = join_url(self.fha['server'], 'api/tradingdates?len=30')
        try:
            r = requests.get(url)
            r.raise_for_status()
            dates = r.json()
            if not dates or len(dates) == 0:
                raise ValueError('no trading dates found')
            date = dates[0]
            for d in reversed(dates):
                if d == today:
                    continue
                pdate = datetime.strptime(d, '%Y-%m-%d')
                if pdate.weekday() == 0:
                    date = d
                    break
        except Exception as e:
            date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
        finally:
            logger.info('upload history deals and other deals since %s', date)
            self.load_his_deals(date)
            self.load_other_deals(date)

    @classmethod
    def load_his_deals(self, date):
        self.normal_account.load_his_deals(date)
        if self.collateral_account:
            self.collateral_account.load_his_deals(date)

    @classmethod
    def load_other_deals(self, date):
        self.normal_account.load_other_deals(date)
        if self.collateral_account:
            self.collateral_account.load_other_deals(date)

    @classmethod
    def check_rzrq(self, code):
        if not self.credit_account:
            return False

        snap = get_rt_price(code)
        data = self.credit_account.get_count_form_data(code, snap['price'], 'B')
        try:
            r = self.jywg.session.post(self.credit_account.count_url, data=data)
            r.raise_for_status()
            robj = r.json()
            return robj['Status'] != -1
        except Exception as e:
            logger.error('check rzrq error: %s', e)
            logger.debug(format_exc())
            return False

    @classmethod
    def buy_new_stocks(self):
        """购买新股"""
        jywg = self.jywg
        if not jywg or not jywg.validate_key:
            logger.info('no valid validateKey: %s', jywg.validate_key if jywg else None)
            return

        url = join_url(jywg.jywg, f'/Trade/GetCanBuyNewStockListV3?validatekey={jywg.validate_key}')
        try:
            response = self.jywg.session.post(url)
            response.raise_for_status()
            robj = response.json()

            if robj.get('NewStockList') and len(robj['NewStockList']) > 0:
                # 过滤符合条件的新股
                filtered_stocks = [
                    stk for stk in robj['NewStockList']
                    if float(stk['Fxj']) < 100 and int(stk['Ksgsx']) > 0
                ]

                data = [
                    {
                        'StockCode': stk['Sgdm'],
                        'StockName': stk['Zqmc'],
                        'Price': stk['Fxj'],
                        'Amount': int(stk['Ksgsx']),
                        'TradeType': 'B',
                        'Market': stk['Market']
                    }
                    for stk in filtered_stocks
                ]

                if len(data) > 0:
                    jdata = json.dumps(data)
                    logger.info('buyNewStocks: %s', jdata)

                    post_url = join_url(jywg.jywg, f'/Trade/SubmitBatTradeV2?validatekey={jywg.validate_key}')
                    headers = {'Content-Type': 'application/json'}
                    post_response = jywg.session.post(post_url, headers=headers, data=jdata)
                    post_response.raise_for_status()
                    robj_post = post_response.json()

                    if robj_post.get('Status') == 0:
                        logger.info('buyNewStocks success: %s', robj_post.get('Message'))
                    else:
                        logger.info('buyNewStocks error: %s', robj_post)
                else:
                    logger.info('buyNewStocks no new stocks to buy!')
            else:
                logger.info(json.dumps(robj))
        except Exception as error:
            logger.error('Error in buyNewStocks: %s', error)
            logger.debug(format_exc())

    @classmethod
    def buy_new_bonds(self):
        """购买新债"""
        jywg = self.jywg
        if not jywg or not jywg.validate_key:
            logger.info('no valid validateKey: %s', jywg.validate_key if jywg else None)
            return

        url = join_url(jywg.jywg, f'/Trade/GetConvertibleBondListV2?validatekey={jywg.validate_key}')
        try:
            response = jywg.session.post(url)
            response.raise_for_status()
            robj = response.json()

            if robj.get('Status') != 0:
                logger.info('unknown error: %s', robj)
                return

            if robj.get('Data') and len(robj['Data']) > 0:
                # 过滤今日可申购的债券
                filtered_bonds = [
                    bondi for bondi in robj['Data']
                    if bondi.get('ExIsToday')
                ]

                data = [
                    {
                        'StockCode': bondi['SUBCODE'],
                        'StockName': bondi['SUBNAME'],
                        'Price': bondi['PARVALUE'],
                        'Amount': bondi['LIMITBUYVOL'],
                        'TradeType': 'B',
                        'Market': bondi['Market']
                    }
                    for bondi in filtered_bonds
                ]

                if len(data) > 0:
                    jdata = json.dumps(data)
                    logger.info('buyNewBonds: %s', jdata)

                    post_url = join_url(jywg.jywg, f'/Trade/SubmitBatTradeV2?validatekey={jywg.validate_key}')
                    headers = {'Content-Type': 'application/json'}
                    post_response = jywg.session.post(post_url, headers=headers, data=jdata)
                    post_response.raise_for_status()
                    robj_post = post_response.json()

                    if robj_post.get('Status') == 0:
                        logger.info('buyNewBonds success: %s', robj_post.get('Message'))
                    else:
                        logger.info('buyNewBonds error: %s', robj_post)
                else:
                    logger.info('buyNewBonds no new bonds to buy!')
            else:
                logger.info('no new bonds: %s', json.dumps(robj))
        except Exception as error:
            logger.error('Error in buyNewBonds: %s', error)
            logger.debug(format_exc())

    @classmethod
    def buy_bond_repurchase(self, code):
        """国债逆回购"""
        jywg = self.jywg
        if not jywg or not jywg.validate_key:
            logger.info('No valid validateKey')
            return

        try:
            price_data = get_rt_price(code)

            # 获取可操作数量
            amount_url = join_url(jywg.jywg, f'/Com/GetCanOperateAmount?validatekey={jywg.validate_key}')
            amount_data = {
                'stockCode': code,
                'price': str(price_data['price']),
                'tradeType': '0S'
            }

            amount_response = jywg.session.post(amount_url, data=amount_data)
            amount_response.raise_for_status()
            amount_result = amount_response.json()

            if (amount_result.get('Status') != 0 or
                not amount_result.get('Data') or
                len(amount_result['Data']) == 0 or
                float(amount_result['Data'][0].get('Kczsl', 0)) <= 0):
                logger.info('No enough funds to repurchase: %s', json.dumps(amount_result))
                return

            price = price_data['price']
            price = price_data['bid5'] if price_data['bid5'] > 0 else price_data['bottom_price']
            count = float(amount_result['Data'][0]['Kczsl'])

            # 进行国债逆回购交易
            repurchase_url = join_url(jywg.jywg, f'/BondRepurchase/SecuritiesLendingRepurchaseTrade?validatekey={jywg.validate_key}')
            repurchase_data = {
                'zqdm': code,
                'rqjg': str(price),
                'rqsl': str(count)
            }

            logger.info('Executing bond repurchase: %s %s %s', code, price, count)
            repurchase_response = jywg.session.post(repurchase_url, data=repurchase_data)
            repurchase_response.raise_for_status()
            repurchase_result = repurchase_response.json()

            if (repurchase_result.get('Status') == 0 and
                repurchase_result.get('Data') and
                len(repurchase_result['Data']) > 0):
                logger.info('Repurchase successful!: %s', json.dumps(repurchase_result))
            else:
                logger.info('Repurchase failed: %s', json.dumps(repurchase_result))
        except Exception as error:
            logger.error('Error in bond repurchase process: %s', error)
            logger.debug(format_exc())

    @classmethod
    def repay_margin_loan(self):
        """偿还融资融券负债"""
        jywg = self.jywg
        validate_key = jywg.validate_key if jywg else None
        if not validate_key:
            return

        assets_url = join_url(jywg.jywg, f'/MarginSearch/GetRzrqAssets?validatekey={validate_key}')
        assets_data = {'hblx': 'RMB'}

        try:
            # 获取融资融券资产信息
            assets_response = jywg.session.post(assets_url, data=assets_data)
            assets_response.raise_for_status()
            assets_result = assets_response.json()

            if assets_result.get('Status') != 0 or not assets_result.get('Data'):
                logger.info('Failed to fetch assets: %s', assets_result)
                return

            assets_data = assets_result['Data']
            for k,v in assets_data.items():
                try:
                    assets_data[k] = float(v)
                except Exception as e:
                    assets_data[k] = v
            logger.debug('获取融资融券资产信息: %s', assets_data)

            # 计算待还款金额
            total = assets_data['Rzfzhj'] + assets_data['Rqxf']
            zjkys = assets_data['Zjkys']
            if total <= 0 or zjkys < 1:
                logger.info('待还款金额: %s 可用金额: %s', total, zjkys)
                return

            pay_amount = total
            if total - zjkys > 0.15:
                date_val = datetime.now().day
                pay_amount = zjkys - 0.2
                if date_val > 25 or date_val < 5:
                    pay_amount -= assets_data['Rzxf'] + assets_data['Rqxf'] + assets_data['Rzxf']

            pay_amount = round(pay_amount, 2)
            if pay_amount <= 0:
                logger.info('Invalid repayment amount: %s', pay_amount)
                return

            # 提交还款请求
            repayment_url = join_url(jywg.jywg, f'/MarginTrade/submitZjhk?validatekey={validate_key}')
            repayment_data = {
                'hbdm': 'RMB',
                'hkje': str(pay_amount),
                'bzxx': ''  # 备注信息
            }

            repayment_response = jywg.session.post(repayment_url, data=repayment_data)
            repayment_response.raise_for_status()
            repayment_result = repayment_response.json()

            if repayment_result.get('Status') == 0:
                repaid_amount = 'Unknown amount'
                if (repayment_result.get('Data') and
                    len(repayment_result['Data']) > 0 and
                    repayment_result['Data'][0].get('Sjhkje')):
                    repaid_amount = repayment_result['Data'][0]['Sjhkje']
                logger.info('Repayment success!: %s', repaid_amount)
            else:
                logger.info('Repayment failed: %s', repayment_result)
        except Exception as error:
            logger.error('Repayment process failed: %s', error)
            logger.debug(format_exc())

    @classmethod
    def buy_stock(self, code, price, count, account, strategies=None):
        if account not in self.all_accounts:
            logger.error('invalid account %s', account)
            return

        if strategies:
            self.all_accounts[account].hold_account.add_watch_stock(code, strategies)

        if count == 0:
            stk = self.all_accounts[account].hold_account.get_stock(code)
            if not stk or 'strategies' not in stk:
                logger.error('no count set and no strategy to calc count %s %s %s %s %s %s', account, code, price, count, strategies, stk)
                return

            count = calc_buy_count(int(stk['strategies'].get('amount', 10000)), price)
            available_money = self.all_accounts[account].available_money
            if count * price > available_money:
                count = calc_buy_count(available_money, price)
                if count * price > available_money:
                    count -= 100

        if count == 0:
            logger.error('count is 0, check available money: %s %s', account, available_money)

        self.all_accounts[account].trade(code, price, count, 'B')

    @classmethod
    def sell_stock(self, code, price, count, account):
        if account not in self.all_accounts:
            logger.error('invalid account %s', account)
            return

        self.all_accounts[account].trade(code, price, count, 'S')

    @classmethod
    def test_trade_api(self, code='601398'):
        snap = get_rt_price(code)
        self.buy_stock(code, snap['bottom_price'], calc_buy_count(1000, snap['bottom_price']), 'normal')

    @classmethod
    def create_deals_for_transfer(self, order):
        """处理担保品划入/划出订单"""
        code = order.get('Zqdm', order.get('Wtjg', '').replace('.', ''))
        date = datetime.now().strftime('%Y-%m-%d')
        price = float(order.get('Cjjg', 0))
        count = int(order.get('Cjsl', 0))
        sid = order.get('Wtbh', '')
        sdetail = { 'code': code, 'price': price, 'count': count, 'sid': sid, 'type': 'S', 'date': date }
        bdetail = { 'code': code, 'price': price, 'count': count, 'sid': sid, 'type': 'B', 'date': date }
        tradeType = order.get('Mmsm', '')
        if tradeType == "担保品划出":
            self.normal_account.extend_stock_buydetail(code, [bdetail])
            self.normal_account._upload_deals(Account.buydetails_to_deals([bdetail]))
            self.collateral_account.extend_stock_buydetail(code, [sdetail])
            self.collateral_account._upload_deals(Account.buydetails_to_deals([sdetail]))
        elif tradeType == "担保品划入":
            self.normal_account.extend_stock_buydetail(code, [sdetail])
            self.normal_account._upload_deals(Account.buydetails_to_deals([sdetail]))
            self.collateral_account.extend_stock_buydetail(code, [bdetail])
            self.collateral_account._upload_deals(Account.buydetails_to_deals([bdetail]))
