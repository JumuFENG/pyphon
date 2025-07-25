import logging
import json
import requests
from datetime import datetime
from misc import get_rt_price, join_url, get_mkt_code, calc_buy_count


logger = logging.getLogger('emtrader')

class Account:
    def __init__(self):
        self.keyword = None
        self.stocks = []
        # {'code': '600475', 'name': '', 'holdCount': 0, 'availableCount': 0, 'strategies': {'holdCost': 14.76, 'holdCount': 100.0, 'strategies': {'grptype': 'GroupStandard', 'strategies': {'0': {'key': 'StrategyBSBE', 'enabled': True, 'guardPrice': 19, 'selltype': 'xsingle', 'disable_sell': False}}, 'transfers': {'0': {'transfer': -1}}, 'amount': 2000, 'buydetail': [{'id': 1055, 'code': 'SH600475', 'date': '2025-07-11', 'count': 100, 'price': 19.14, 'sid': '68879', 'type': 'B'}], 'buydetail_full': [{'id': 1115, 'code': 'SH600475', 'date': '2025-07-11', 'count': 100, 'price': 19.14, 'sid': '68879', 'type': 'B'}]}}}
        self.fundcode = '511880'
        self.hacc = None
        self.pure_assets = 0.0
        self.available_money = 0.0
        self.trading_records = []
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

    def load_watchings(self):
        wurl = join_url(accld.fha['server'], 'stock?act=watchings&acc=' + self.keyword)
        r = requests.get(wurl, headers=accld.fha['headers'])
        r.raise_for_status()
        watchings = r.json()
        if not watchings:
            logger.info(self.keyword, 'loadWatchings no watchings')
            return

        for code, strategies in watchings.items():
            self.add_watch_stock(code[-6:], strategies)

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

            def extend_buydetail(buydetail, exdetail):
                if not isinstance(buydetail, list):
                    return
                if not isinstance(exdetail, list):
                    return
                for bd in exdetail:
                    exbd = next((x for x in buydetail if x['sid'] == bd['sid'] and x['date'] == bd['date'] and x['type'] == bd['type']), None)
                    if exbd:
                        continue
                    buydetail.append(bd)

            if 'buydetail' in strgrp:
                extend_buydetail(stock['buydetail'], strgrp['buydetail'])
            if 'buydetail_full' in strgrp:
                extend_buydetail(stock['buydetail_full'], strgrp['buydetail_full'])
            return

        self.stocks.append({
            'code': code, 'name': '', 'holdCount': 0, 'availableCount': 0,
            'strategies': strgrp, 'buydetail': strgrp.get('buydetail', []),
            'buydetail_full': strgrp.get('buydetail_full', [])
        })

    def check_orders(self):
        # 查询当日订单
        pass

    def load_deals(self):
        # 查询当日订单，并将当日成交记录上传
        pass

    def _upload_deals(self, deals):
        pass

    def load_his_deals(self, date):
        # 查询date至今所有历史订单(买卖订单)
        pass

    def load_other_deals(self, date):
        # 查询date至今所有其它订单(非买卖订单)
        pass

    def buy_fund_before_close(self):
        pass

    def get_assets_and_positions(self):
        pass

    def get_assets(self):
        pass

    def get_positions(self):
        pass

    def parse_position(self, position):
        code = position.get('Zqdm')
        name = position.get('Zqmc')
        hold_count = int(position.get('Zqsl', 0))
        available_count = int(position.get('Kysl', 0))
        if hold_count - available_count != 0 and datetime.now().hour >= 15:
            available_count = hold_count
        hold_cost = position.get('Cbjg')
        latest_price = position.get('Zxjg')
        return {
            'code': code,
            'name': name,
            'holdCount': hold_count,
            'holdCost': hold_cost,
            'availableCount': available_count,
            'latestPrice': latest_price
        }

    def load_assets(self):
        s, p = self.get_assets_and_positions()
        self.on_assets_loaded(s)
        self.on_positions_loaded(p)

    def on_assets_loaded(self, assets):
        pass

    def on_positions_loaded(self, positions):
        pass

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
            return int(robj['data']['Data']['Kmml'])
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
            if count > 1:
                final_count = 100 * (acount // 100 / count)
            if final_count < 100:
                logger.error('invalid count: %d, available count: %s', final_count, acount)
                return

        data = self.get_form_data(code, price, final_count, bstype)
        try:
            r = self.jysession.post(self.trade_url, data=data)
            r.raise_for_status()
            robj = r['data']
            if robj['Status'] != 0 or len(robj['Data']) == 0:
                logger.error('submit trade error: %s, %s, %s', code, bstype, robj)
                return
            if bstype == 'B':
                self.available_money -= price * final_count
            elif bstype == 'S':
                self.available_money += price * final_count
            self.hold_account.trading_records.append({'code': code, 'price': price, 'count': count, 'sid': robj['Data'][0]['Wtbh'], 'type': bstype})
        except Exception as e:
            logger.error('submit trade error: %s, %s, %s', code, bstype, e)


class NormalAccount(Account):
    def __init__(self):
        super().__init__()
        self.keyword = 'normal'

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
            return None, None

    def get_assets(self):
        return self.get_assets_and_positions()[0]

    def on_assets_loaded(self, assets):
        if assets:
            self.pure_assets = float(assets['Zzc'])
            self.available_money = float(assets['Kyzj'])

    def get_positions(self):
        return self.get_assets_and_positions()[1]

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
            return None

    def on_assets_loaded(self, assets):
        if not assets:
            return
        self.pure_assets = float(assets['Zzc']) - float(assets['Zfz'])
        self.available_money = float(assets['Zjkys'])
        if accld.credit_account:
            accld.credit_account.available_money = float(assets['Bzjkys'])

    def get_positions(self):
        url = join_url(self.wgdomain, f'/MarginSearch/GetRzrqPositions?validatekey={self.valkey}')
        try:
            r = self.jysession.post(url)
            r.raise_for_status()
            a = r.json()
            return a['Data']
        except Exception as e:
            logger.error(r.text)
            logger.error(e)
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

    def check_orders(self):
        pass


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
    def load_his_deals(self):
        pass

    @classmethod
    def load_other_deals(self):
        pass

    @classmethod
    def check_rzrq(self, code):
        pass

    @classmethod
    def buy_new_stocks(self):
        """购买新股"""
        jywg = self.jywg
        if not jywg or not jywg.validate_key:
            logger.info('no valid validateKey: %s', jywg.validate_key if jywg else None)
            return

        url = join_url(jywg.jywg, f'/Trade/GetCanBuyNewStockListV3?validatekey={jywg.validate_key}')
        try:
            response = self.jysession.post(url)
            response.raise_for_status()
            robj = response.json()

            if robj.get('NewStockList') and len(robj['NewStockList']) > 0:
                # 过滤符合条件的新股
                filtered_stocks = [
                    stk for stk in robj['NewStockList']
                    if stk['Fxj'] - 100 < 0 and stk['Ksgsx'] > 0
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

    @classmethod
    def buy_bond_repurchase(self, code):
        """国债逆回购"""
        jywg = self.jywg
        if not jywg or not jywg.validate_key:
            logger.info('No valid validateKey')
            return

        try:
            price_data = get_rt_price(code)
            price = price_data['price']
            price = price_data['bottom_price'] if price_data['buysells']['buy5'] == '-' else price_data['buysells']['buy5']

            # 获取可操作数量
            amount_url = join_url(jywg.jywg, f'/Com/GetCanOperateAmount?validatekey={jywg.validate_key}')
            amount_data = {
                'stockCode': code,
                'price': str(price),
                'tradeType': '0S'
            }

            amount_response = jywg.session.post(amount_url, data=amount_data)
            amount_response.raise_for_status()
            amount_result = amount_response.json()

            if (amount_result.get('Status') != 0 or
                not amount_result.get('Data') or
                len(amount_result['Data']) == 0 or
                amount_result['Data'][0].get('Kczsl', 0) <= 0):
                logger.info('No enough funds to repurchase: %s', json.dumps(amount_result))
                return

            count = amount_result['Data'][0]['Kczsl']

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
            logger.info('Error in bond repurchase process: %s', error)

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

            assets_data_obj = assets_result['Data']

            # 计算待还款金额
            total = -(-assets_data_obj.get('Rzfzhj', 0) - assets_data_obj.get('Rqxf', 0))
            if total <= 0 or assets_data_obj.get('Zjkys', 0) - 1 < 0:
                logger.info('待还款金额: %s 可用金额: %s', total, assets_data_obj.get('Zjkys', 0))
                return

            pay_amount = total
            if total - assets_data_obj.get('Zjkys', 0) > 0.1:
                date_val = datetime.now().day
                if date_val > 25 or date_val < 5:
                    pay_amount = (assets_data_obj.get('Zjkys', 0) -
                                assets_data_obj.get('Rzxf', 0) -
                                assets_data_obj.get('Rqxf', 0) -
                                assets_data_obj.get('Rzxf', 0))
                else:
                    pay_amount = round(assets_data_obj.get('Zjkys', 0) - 0.11, 2)

            pay_amount = float(pay_amount)
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
            logger.info('Repayment process failed: %s', error)

    @classmethod
    def buy_stock(self, code, price, count, account, strategies=None):
        if account not in self.all_accounts:
            logger.error('invalid account %s', account)
            return

        if strategies:
            self.all_accounts[account].hold_account.add_watch_stock(code, strategies)
        
        if count == 0:
            stk = self.all_accounts[account].hold_account.get_stock(code)
            if not stk or ['strategies'] not in stk:
                logger.error('no count set and no strategy to calc count %s %s %s %s %s %s', account, code, price, count, strategies, stk)
                return

            count = calc_buy_count(stk['strategies'].get('amount', 10000), price)
            available_money = self.all_accounts[account].available_money
            if count * price > available_money:
                count = calc_buy_count(calc_buy_count(available_money, price))
                if count * price > available_money:
                    count -= 100

        if count == 0:
            logger.error('count is 0, check available money: %s', available_money)

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
