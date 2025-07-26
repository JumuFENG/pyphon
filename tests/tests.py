import unittest
import sys
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pyphon'))

from pyphon.accounts import Account, NormalAccount, CollateralAccount, TrackingAccount, accld
from pyphon.misc import delay_seconds, join_url, safe_float, get_mkt_code, calc_buy_count, get_stock_snapshot


class TestAccount(Account):
    """测试用的具体 Account 实现"""

    @property
    def order_url(self):
        return "http://test.com/order"

    @property
    def hisdeals_url(self):
        return "http://test.com/hisdeals"

    @property
    def hissxl_url(self):
        return "http://test.com/hissxl"

    def buy_fund_before_close(self):
        pass

    def get_assets_and_positions(self):
        return {}, []

    def get_assets(self):
        return {}

    def get_positions(self):
        return []

    @property
    def count_url(self):
        return "http://test.com/count"

    @property
    def trade_url(self):
        return "http://test.com/trade"


class TestAccountMethods(unittest.TestCase):
    """测试 Account 类中不涉及 HTTP 请求的方法"""

    def setUp(self):
        self.account = Account()
        self.account.stocks = [
            {'code': '600000', 'name': '浦发银行', 'holdCount': 100, 'availableCount': 100},
            {'code': '000001', 'name': '平安银行', 'holdCount': 200, 'availableCount': 150}
        ]

    def test_get_stock_exists(self):
        """测试获取存在的股票"""
        stock = self.account.get_stock('600000')
        self.assertIsNotNone(stock)
        self.assertEqual(stock['name'], '浦发银行')
        self.assertEqual(stock['holdCount'], 100)

    def test_get_stock_not_exists(self):
        """测试获取不存在的股票"""
        stock = self.account.get_stock('999999')
        self.assertIsNone(stock)

    def test_extend_buydetail_valid_lists(self):
        """测试扩展买入详情 - 有效列表"""
        buydetail = [
            {'sid': '001', 'date': '2025-01-01', 'type': 'B', 'count': 100}
        ]
        exdetail = [
            {'sid': '002', 'date': '2025-01-02', 'type': 'B', 'count': 200},
            {'sid': '001', 'date': '2025-01-01', 'type': 'B', 'count': 100}  # 重复项
        ]

        Account.extend_buydetail(buydetail, exdetail)

        # 应该只添加不重复的项
        self.assertEqual(len(buydetail), 2)
        self.assertTrue(any(item['sid'] == '002' for item in buydetail))

    def test_extend_buydetail_invalid_input(self):
        """测试扩展买入详情 - 无效输入"""
        buydetail = []

        # 测试 exdetail 不是列表
        Account.extend_buydetail(buydetail, "not a list")
        self.assertEqual(len(buydetail), 0)

        # 测试 buydetail 不是列表
        Account.extend_buydetail("not a list", [])
        # 不应该抛出异常

    def test_extend_stock_buydetail(self):
        """测试扩展股票买入详情"""
        exdetail = [
            {'sid': '003', 'date': '2025-01-03', 'type': 'B', 'count': 300}
        ]

        self.account.extend_stock_buydetail('600000', exdetail)

        stock = self.account.get_stock('600000')
        self.assertIn('buydetail', stock)
        self.assertIn('buydetail_full', stock)
        self.assertEqual(len(stock['buydetail']), 1)
        self.assertEqual(stock['buydetail'][0]['sid'], '003')

    def test_extend_stock_buydetail_nonexistent_stock(self):
        """测试扩展不存在股票的买入详情"""
        exdetail = [{'sid': '004', 'date': '2025-01-04', 'type': 'B', 'count': 400}]

        # 不应该抛出异常
        self.account.extend_stock_buydetail('999999', exdetail)

    def test_tradeType_from_Mmsm(self):
        """测试从交易描述获取交易类型"""
        # 测试卖出类型
        self.assertEqual(self.account.tradeType_from_Mmsm('证券卖出'), 'S')
        self.assertEqual(self.account.tradeType_from_Mmsm('担保品划出'), 'S')

        # 测试买入类型
        self.assertEqual(self.account.tradeType_from_Mmsm('证券买入'), 'B')
        self.assertEqual(self.account.tradeType_from_Mmsm('担保品划入'), 'B')
        self.assertEqual(self.account.tradeType_from_Mmsm('配售申购'), 'B')
        self.assertEqual(self.account.tradeType_from_Mmsm('配股缴款'), 'B')
        self.assertEqual(self.account.tradeType_from_Mmsm('网上认购'), 'B')

        # 测试忽略类型
        self.assertIsNone(self.account.tradeType_from_Mmsm('融券'))

        # 测试未知类型
        self.assertIsNone(self.account.tradeType_from_Mmsm('未知类型'))

    def test_parse_position(self):
        """测试解析持仓信息"""
        position = {
            'Zqdm': '600000',
            'Zqmc': '浦发银行',
            'Zqsl': '100',
            'Kysl': '80',
            'Cbjg': '12.50',
            'Zxjg': '13.20'
        }

        with patch('pyphon.accounts.datetime') as mock_datetime:
            mock_datetime.now.return_value.hour = 16  # 下午4点

            result = self.account.parse_position(position)

            expected = {
                'code': '600000',
                'name': '浦发银行',
                'holdCount': 100,
                'holdCost': '12.50',
                'availableCount': 100,  # 应该等于holdCount，因为是下午4点后
                'latestPrice': '13.20'
            }

            self.assertEqual(result, expected)

    def test_parse_position_before_close(self):
        """测试收盘前解析持仓信息"""
        position = {
            'Zqdm': '600000',
            'Zqmc': '浦发银行',
            'Zqsl': '100',
            'Kysl': '80',
            'Cbjg': '12.50',
            'Zxjg': '13.20'
        }

        with patch('pyphon.accounts.datetime') as mock_datetime:
            mock_datetime.now.return_value.hour = 14  # 下午2点

            result = self.account.parse_position(position)

            self.assertEqual(result['availableCount'], 80)  # 应该保持原值

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_count_form_data(self, mock_get_mkt_code):
        """测试获取数量表单数据"""
        mock_get_mkt_code.return_value = 'SH'

        result = self.account.get_count_form_data('600000', 12.50, 'B')

        expected = {
            'stockCode': '600000',
            'price': 12.50,
            'tradeType': 'B',
            'market': 'HA',
            'stockName': '',
            'gddm': ''
        }

        self.assertEqual(result, expected)

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_form_data(self, mock_get_mkt_code):
        """测试获取表单数据"""
        mock_get_mkt_code.return_value = 'SZ'

        result = self.account.get_form_data('000001', 10.50, 100, 'S')

        expected = {
            'stockCode': '000001',
            'price': 10.50,
            'amount': 100,
            'tradeType': 'S',
            'market': 'SA'
        }

        self.assertEqual(result, expected)

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_form_data_bj_market(self, mock_get_mkt_code):
        """测试北交所股票的表单数据"""
        mock_get_mkt_code.return_value = 'BJ'

        result = self.account.get_form_data('430001', 5.50, 200, 'B')

        expected = {
            'stockCode': '430001',
            'price': 5.50,
            'amount': 200,
            'tradeType': '0B',  # BJ市场需要加前缀0
            'market': 'B'
        }

        self.assertEqual(result, expected)


class TestNormalAccountMethods(unittest.TestCase):
    """测试 NormalAccount 类的特定方法"""

    def setUp(self):
        self.account = NormalAccount()

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_form_data_with_zqmc(self, mock_get_mkt_code):
        """测试普通账户的表单数据包含zqmc字段"""
        mock_get_mkt_code.return_value = 'SH'

        result = self.account.get_form_data('600000', 12.50, 100, 'B')

        self.assertIn('zqmc', result)
        self.assertEqual(result['zqmc'], '')


class TestCollateralAccountMethods(unittest.TestCase):
    """测试 CollateralAccount 类的特定方法"""

    def setUp(self):
        self.account = CollateralAccount()

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_count_form_data_with_margin_fields(self, mock_get_mkt_code):
        """测试融资融券账户的数量表单数据包含特定字段"""
        mock_get_mkt_code.return_value = 'SH'

        result = self.account.get_count_form_data('600000', 12.50, 'B')

        self.assertIn('xyjylx', result)
        self.assertIn('stockName', result)
        self.assertIn('moneyType', result)
        self.assertEqual(result['xyjylx'], '6')  # 买入交易类型
        self.assertEqual(result['moneyType'], 'RMB')

    @patch('pyphon.accounts.get_mkt_code')
    def test_get_form_data_with_margin_fields(self, mock_get_mkt_code):
        """测试融资融券账户的表单数据包含特定字段"""
        mock_get_mkt_code.return_value = 'SZ'

        result = self.account.get_form_data('000001', 10.50, 100, 'S')

        self.assertIn('stockName', result)
        self.assertIn('xyjylx', result)
        self.assertEqual(result['xyjylx'], '7')  # 卖出交易类型


class TestMiscFunctions(unittest.TestCase):
    """测试 misc.py 中的工具函数"""

    def test_delay_seconds(self):
        """测试计算时间间隔"""
        # 模拟当前时间为上午10:30:00
        mock_now = datetime(2025, 1, 15, 10, 30, 0)

        with patch('pyphon.misc.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # 测试到下午3点的间隔
            result = delay_seconds('15:00:00')
            expected = 4.5 * 3600  # 4.5小时
            self.assertEqual(result, expected)

            # 测试到上午9点的间隔（第二天）
            result = delay_seconds('09:00')
            expected = -1.5 * 3600  # -1.5小时（已过去）
            self.assertEqual(result, expected)

    def test_join_url(self):
        """测试URL拼接"""
        # 测试正常情况
        self.assertEqual(join_url('http://example.com', 'api/test'), 'http://example.com/api/test')

        # 测试服务器URL以/结尾
        self.assertEqual(join_url('http://example.com/', 'api/test'), 'http://example.com/api/test')

        # 测试路径以/开头
        self.assertEqual(join_url('http://example.com', '/api/test'), 'http://example.com/api/test')

        # 测试两者都有/
        self.assertEqual(join_url('http://example.com/', '/api/test'), 'http://example.com/api/test')

    def test_safe_float(self):
        """测试安全浮点数转换"""
        # 测试正常转换
        self.assertEqual(safe_float('12.34'), 12.34)
        self.assertEqual(safe_float(56.78), 56.78)
        self.assertEqual(safe_float('0'), 0.0)

        # 测试异常情况
        self.assertEqual(safe_float('invalid'), 0.0)
        self.assertEqual(safe_float(None), 0.0)
        self.assertEqual(safe_float(''), 0.0)

    def test_get_mkt_code(self):
        """测试获取市场代码"""
        # 测试北交所
        self.assertEqual(get_mkt_code('430001'), 'BJ')
        self.assertEqual(get_mkt_code('800001'), 'BJ')
        self.assertEqual(get_mkt_code('920001'), 'BJ')

        # 测试上交所
        self.assertEqual(get_mkt_code('600000'), 'SH')
        self.assertEqual(get_mkt_code('500001'), 'SH')
        self.assertEqual(get_mkt_code('700001'), 'SH')
        self.assertEqual(get_mkt_code('900001'), 'SH')
        self.assertEqual(get_mkt_code('110001'), 'SH')
        self.assertEqual(get_mkt_code('113001'), 'SH')
        self.assertEqual(get_mkt_code('118001'), 'SH')
        self.assertEqual(get_mkt_code('132001'), 'SH')
        self.assertEqual(get_mkt_code('204001'), 'SH')

        # 测试深交所
        self.assertEqual(get_mkt_code('000001'), 'SZ')
        self.assertEqual(get_mkt_code('300001'), 'SZ')
        self.assertEqual(get_mkt_code('002001'), 'SZ')

    def test_get_mkt_code_invalid_length(self):
        """测试无效长度的股票代码"""
        with self.assertRaises(AssertionError):
            get_mkt_code('12345')  # 长度不足6位

        with self.assertRaises(AssertionError):
            get_mkt_code('1234567')  # 长度超过6位

    def test_calc_buy_count(self):
        """测试计算买入数量"""
        # 测试正常情况
        result = calc_buy_count(1000, 10.0)  # 1000元，10元/股，正好10手
        self.assertEqual(result, 100)  # 应该买100股

        # 测试1500元买10元股票的情况
        # ct = (1500/100)/10 = 1.5
        # floor(1.5)*100 = 100, ceil(1.5)*100 = 200
        # 1500 - 10*100 = 500, 10*200 - 1500 = 500
        # 两者相等，选择floor，所以是100股
        result = calc_buy_count(1500, 10.0)  # 1500元，10元/股
        self.assertEqual(result, 100)  # 应该买100股

        # 测试1600元买10元股票的情况
        # ct = (1600/100)/10 = 1.6
        # floor(1.6)*100 = 100, ceil(1.6)*100 = 200
        # 1600 - 10*100 = 600, 10*200 - 1600 = 400
        # ceil更接近，所以是200股
        result = calc_buy_count(1600, 10.0)  # 1600元，10元/股
        self.assertEqual(result, 200)  # 应该买200股（向上取整更接近）

        # 测试金额不足100股的情况
        result = calc_buy_count(500, 10.0)  # 500元，10元/股，只能买50股
        self.assertEqual(result, 100)  # 最少买100股

    def test_get_stock_snapshot(self):
        """测试 get_stock_snapshot 的边界情况"""
        result = get_stock_snapshot('600000')
        self.assertIsInstance(result['price'], float)
        self.assertIsInstance(result['top_price'], float)
        self.assertIsInstance(result['bottom_price'], float)
        self.assertIsInstance(result['buysells'], dict)


class TestAccountProperties(unittest.TestCase):
    """测试 Account 类的属性方法"""

    def setUp(self):
        self.account = Account()

    def test_hold_account_property(self):
        """测试 hold_account 属性"""
        # 当 hacc 为 None 时，返回自身
        self.assertEqual(self.account.hold_account, self.account)

        # 当 hacc 不为 None 时，返回 hacc
        mock_hacc = Account()
        self.account.hacc = mock_hacc
        self.assertEqual(self.account.hold_account, mock_hacc)

    @patch('pyphon.accounts.accld')
    def test_jysession_property(self, mock_accld):
        """测试 jysession 属性"""
        # 当 accld.jywg 存在时
        mock_session = MagicMock()
        mock_accld.jywg.session = mock_session
        self.assertEqual(self.account.jysession, mock_session)

        # 当 accld.jywg 不存在时
        mock_accld.jywg = None
        self.assertIsNone(self.account.jysession)

    @patch('pyphon.accounts.accld')
    def test_wgdomain_property(self, mock_accld):
        """测试 wgdomain 属性"""
        # 当 accld.jywg 存在时
        mock_domain = 'http://example.com'
        mock_accld.jywg.jywg = mock_domain
        self.assertEqual(self.account.wgdomain, mock_domain)

        # 当 accld.jywg 不存在时
        mock_accld.jywg = None
        self.assertIsNone(self.account.wgdomain)

    @patch('pyphon.accounts.accld')
    def test_valkey_property(self, mock_accld):
        """测试 valkey 属性"""
        # 当 accld.jywg 存在时
        mock_key = 'test_validate_key'
        mock_accld.jywg.validate_key = mock_key
        self.assertEqual(self.account.valkey, mock_key)

        # 当 accld.jywg 不存在时
        mock_accld.jywg = None
        self.assertIsNone(self.account.valkey)


class TestAccountAddWatchStock(unittest.TestCase):
    """测试 Account 类的 add_watch_stock 方法"""

    def setUp(self):
        self.account = Account()
        self.account.stocks = []

    def test_add_watch_stock_new_stock(self):
        """测试添加新的监控股票"""
        strgrp = {
            'strategies': {'0': {'key': 'StrategyBSBE', 'enabled': True}},
            'amount': 1000,
            'buydetail': [{'id': 1, 'code': 'SH600000', 'count': 100}],
            'buydetail_full': [{'id': 1, 'code': 'SH600000', 'count': 100}]
        }

        self.account.add_watch_stock('600000', strgrp)

        self.assertEqual(len(self.account.stocks), 1)
        stock = self.account.stocks[0]
        self.assertEqual(stock['code'], '600000')
        self.assertEqual(stock['holdCount'], 0)
        self.assertEqual(stock['strategies'], strgrp)

    def test_add_watch_stock_existing_no_hold(self):
        """测试添加已存在但无持仓的股票"""
        # 先添加一个无持仓的股票
        self.account.stocks = [
            {'code': '600000', 'name': '浦发银行', 'holdCount': 0, 'availableCount': 0}
        ]

        strgrp = {
            'strategies': {'0': {'key': 'StrategyBSBE', 'enabled': True}},
            'amount': 1000
        }

        self.account.add_watch_stock('600000', strgrp)

        # 应该更新策略
        self.assertEqual(len(self.account.stocks), 1)
        self.assertEqual(self.account.stocks[0]['strategies'], strgrp)

    def test_add_watch_stock_existing_with_hold(self):
        """测试添加已存在且有持仓的股票"""
        # 先添加一个有持仓的股票
        existing_strategies = {
            'strategies': {'0': {'key': 'ExistingStrategy', 'enabled': True}},
            'amount': 500
        }
        self.account.stocks = [
            {
                'code': '600000', 'name': '浦发银行', 'holdCount': 100,
                'availableCount': 100, 'strategies': existing_strategies
            }
        ]

        new_strgrp = {
            'strategies': {'0': {'key': 'NewStrategy', 'enabled': True}},
            'amount': 1000
        }

        self.account.add_watch_stock('600000', new_strgrp)

        # 应该合并策略
        stock = self.account.stocks[0]
        self.assertEqual(len(stock['strategies']['strategies']), 2)
        self.assertEqual(stock['strategies']['amount'], 1000)  # 更新金额


class TestMiscEdgeCases(unittest.TestCase):
    """测试 misc.py 中的边界情况"""

    def test_delay_seconds_edge_cases(self):
        """测试 delay_seconds 的边界情况"""
        mock_now = datetime(2025, 1, 15, 10, 30, 45)

        with patch('pyphon.misc.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # 测试只有小时的情况
            result = delay_seconds('15')
            expected = (15 - 10) * 3600 - 30 * 60 - 45  # 4小时29分15秒
            self.assertEqual(result, expected)

            # 测试小时和分钟的情况
            result = delay_seconds('15:30')
            expected = (15 - 10) * 3600 + (30 - 30) * 60 - 45  # 4小时59分15秒
            self.assertEqual(result, expected)

    def test_calc_buy_count_edge_cases(self):
        """测试 calc_buy_count 的边界情况"""
        # 测试价格很高的情况
        result = calc_buy_count(1000, 500.0)  # 1000元买500元的股票
        self.assertEqual(result, 100)  # 最少100股

        # 测试价格很低的情况
        result = calc_buy_count(10000, 1.0)  # 10000元买1元的股票
        # ct = (10000/100)/1 = 100
        # floor(100)*100 = 10000, ceil(100)*100 = 10000
        # 相等，选择floor
        self.assertEqual(result, 10000)

        # 测试ct刚好等于1的情况
        result = calc_buy_count(1000, 10.0)  # ct = 1.0
        self.assertEqual(result, 100)



class TestAccountCheckOrders(unittest.TestCase):
    """测试 Account.check_orders 方法"""

    def setUp(self):
        self.account = Account()
        self.account.keyword = 'test_account'
        self.account.trading_records = []

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.delay_seconds')
    @patch('pyphon.accounts.accld')
    def test_check_orders_success_deals(self, mock_accld, mock_delay_seconds, mock_datetime):
        """测试成功处理已成交订单"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'
        mock_delay_seconds.return_value = -3600  # 已过15:00

        # Mock get_orders 返回数据
        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '证券买入',
                'Wtzt': '已成',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            },
            {
                'Zqdm': '000001',
                'Mmsm': '证券卖出',
                'Wtzt': '已撤',
                'Cjjg': 10.80,
                'Cjsl': 200,
                'Wtbh': 'ORDER002',
                'Zqmc': '平安银行'
            }
        ]

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            with patch.object(self.account, 'extend_stock_buydetail') as mock_extend:
                result = self.account.check_orders()

                # 验证返回结果
                self.assertIn('600000', result)
                self.assertIn('000001', result)
                self.assertEqual(len(result['600000']), 1)
                self.assertEqual(len(result['000001']), 1)

                # 验证买入订单
                buy_deal = result['600000'][0]
                self.assertEqual(buy_deal['code'], '600000')
                self.assertEqual(buy_deal['price'], 12.50)
                self.assertEqual(buy_deal['count'], 100)
                self.assertEqual(buy_deal['type'], 'B')
                self.assertEqual(buy_deal['sid'], 'ORDER001')

                # 验证卖出订单
                sell_deal = result['000001'][0]
                self.assertEqual(sell_deal['code'], '000001')
                self.assertEqual(sell_deal['type'], 'S')

                # 验证调用了extend_stock_buydetail
                self.assertEqual(mock_extend.call_count, 2)

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.delay_seconds')
    def test_check_orders_partial_deals_before_close(self, mock_delay_seconds, mock_datetime):
        """测试收盘前的部成订单处理"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'
        mock_delay_seconds.return_value = 3600  # 未到15:00

        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '证券买入',
                'Wtzt': '部成',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            }
        ]

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            result = self.account.check_orders()

            # 部成订单在收盘前不应该被处理
            self.assertEqual(len(result), 0)

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.delay_seconds')
    def test_check_orders_partial_deals_after_close(self, mock_delay_seconds, mock_datetime):
        """测试收盘后的部成订单处理"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'
        mock_delay_seconds.return_value = -3600  # 已过15:00

        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '证券买入',
                'Wtzt': '部成',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            }
        ]

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            with patch.object(self.account, 'extend_stock_buydetail'):
                result = self.account.check_orders()

                # 部成订单在收盘后应该被处理
                self.assertIn('600000', result)
                self.assertEqual(len(result['600000']), 1)

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.accld')
    def test_check_orders_transfer_deals(self, mock_accld, mock_datetime):
        """测试担保品划转订单处理"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'

        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '担保品划入',
                'Wtzt': '已确认',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            }
        ]

        mock_accld.create_deals_for_transfer = Mock()

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            result = self.account.check_orders()

            # 担保品划转不应该在结果中
            self.assertEqual(len(result), 0)
            # 应该调用create_deals_for_transfer
            mock_accld.create_deals_for_transfer.assert_called_once()

    @patch('pyphon.accounts.datetime')
    def test_check_orders_ignore_subscription(self, mock_datetime):
        """测试忽略配售申购订单"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'

        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '配售申购',
                'Wtzt': '已报',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            }
        ]

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            result = self.account.check_orders()

            # 配售申购订单应该被忽略
            self.assertEqual(len(result), 0)

    @patch('pyphon.accounts.datetime')
    def test_check_orders_remove_trading_records(self, mock_datetime):
        """测试移除已成交的交易记录"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'

        # 添加一个交易记录
        self.account.trading_records = [
            {'code': '600000', 'type': 'B', 'sid': 'ORDER001'}
        ]

        mock_orders_data = [
            {
                'Zqdm': '600000',
                'Mmsm': '证券买入',
                'Wtzt': '已成',
                'Cjjg': 12.50,
                'Cjsl': 100,
                'Wtbh': 'ORDER001',
                'Zqmc': '浦发银行'
            }
        ]

        with patch.object(self.account, 'get_orders', return_value=mock_orders_data):
            with patch.object(self.account, 'extend_stock_buydetail'):
                result = self.account.check_orders()

                # 交易记录应该被移除
                self.assertEqual(len(self.account.trading_records), 0)


class TestAccountArchiveDeals(unittest.TestCase):
    """测试 Account.archive_deals 方法"""

    def setUp(self):
        self.account = Account()
        self.account.stocks = [
            {
                'code': '600000',
                'name': '浦发银行',
                'holdCount': 0,
                'availableCount': 0,
                'buydetail': [
                    {'type': 'B', 'count': 100, 'price': 10.0, 'sid': 'BUY001'},
                    {'type': 'B', 'count': 200, 'price': 12.0, 'sid': 'BUY002'},
                    {'type': 'S', 'count': 150, 'price': 11.0, 'sid': 'SELL001'}
                ]
            }
        ]

    def test_archive_deals_empty_deals(self):
        """测试空交易列表"""
        self.account.archive_deals(None)
        self.account.archive_deals([])
        # 不应该抛出异常

    def test_archive_deals_normal_case(self):
        """测试正常的交易归档"""
        deals = ['600000']

        self.account.archive_deals(deals)

        stock = self.account.get_stock('600000')
        # 卖出150股，应该先匹配价格低的100股，再匹配50股从200股中
        # 剩余buydetail应该是150股价格12.0的
        self.assertEqual(len(stock['buydetail']), 1)
        self.assertEqual(stock['buydetail'][0]['count'], 150)  # 200 - 50 = 150
        self.assertEqual(stock['buydetail'][0]['price'], 12.0)

        # holdCount和availableCount应该更新
        self.assertEqual(stock['holdCount'], 150)
        self.assertEqual(stock['availableCount'], 150)

    def test_archive_deals_exact_match(self):
        """测试精确匹配的交易归档"""
        # 修改股票数据，使卖出数量正好匹配买入数量
        stock = self.account.get_stock('600000')
        stock['buydetail'] = [
            {'type': 'B', 'count': 100, 'price': 10.0, 'sid': 'BUY001'},
            {'type': 'B', 'count': 200, 'price': 12.0, 'sid': 'BUY002'},
            {'type': 'S', 'count': 100, 'price': 11.0, 'sid': 'SELL001'}  # 精确匹配100股
        ]

        deals = ['600000']
        self.account.archive_deals(deals)

        # 应该移除100股的买入记录
        self.assertEqual(len(stock['buydetail']), 1)
        self.assertEqual(stock['buydetail'][0]['count'], 200)
        self.assertEqual(stock['buydetail'][0]['price'], 12.0)

    def test_archive_deals_oversell(self):
        """测试卖出数量超过买入数量的情况"""
        stock = self.account.get_stock('600000')
        stock['buydetail'] = [
            {'type': 'B', 'count': 100, 'price': 10.0, 'sid': 'BUY001'},
            {'type': 'S', 'count': 200, 'price': 11.0, 'sid': 'SELL001'}  # 卖出超过买入
        ]

        deals = ['600000']

        with patch('pyphon.accounts.logger') as mock_logger:
            self.account.archive_deals(deals)

            # 应该记录错误日志
            mock_logger.error.assert_called()

            # buydetail应该为空（因为出现错误，跳过处理）
            self.assertEqual(len(stock['buydetail']), 2)  # 保持原状

    def test_archive_deals_nonexistent_stock(self):
        """测试不存在的股票代码"""
        deals = ['999999']  # 不存在的股票

        # 不应该抛出异常
        self.account.archive_deals(deals)


class TestAccountGetHistoryDeals(unittest.TestCase):
    """测试 Account.get_history_deals 方法"""

    def setUp(self):
        self.account = Account()

    @patch('pyphon.accounts.datetime')
    def test_get_history_deals_string_date(self, mock_datetime):
        """测试字符串日期输入"""
        mock_datetime.now.return_value = datetime(2025, 1, 15)
        mock_datetime.strptime = datetime.strptime

        mock_deals_data = [{'order_id': '001'}, {'order_id': '002'}]

        with patch.object(self.account, 'fetch_batches_deal_data', return_value=mock_deals_data) as mock_fetch:
            result = self.account.get_history_deals('http://test.com', '2024-12-01')

            # 应该调用fetch_batches_deal_data
            self.assertTrue(mock_fetch.called)
            # 返回结果应该包含所有数据
            self.assertEqual(len(result), 2)

    @patch('pyphon.accounts.datetime')
    def test_get_history_deals_datetime_date(self, mock_datetime):
        """测试datetime对象日期输入"""
        mock_datetime.now.return_value = datetime(2025, 1, 15)

        mock_deals_data = [{'order_id': '001'}]

        with patch.object(self.account, 'fetch_batches_deal_data', return_value=mock_deals_data) as mock_fetch:
            start_date = datetime(2024, 12, 1)
            result = self.account.get_history_deals('http://test.com', start_date)

            self.assertTrue(mock_fetch.called)
            self.assertEqual(len(result), 1)

    @patch('pyphon.accounts.datetime')
    def test_get_history_deals_date_sections(self, mock_datetime):
        """测试日期分段逻辑"""
        mock_datetime.now.return_value = datetime(2025, 1, 15)
        mock_datetime.strptime = datetime.strptime

        with patch.object(self.account, 'fetch_batches_deal_data', return_value=[]) as mock_fetch:
            # 测试跨度超过90天的日期范围
            self.account.get_history_deals('http://test.com', '2024-10-01')

            # 应该被分成多个时间段调用
            self.assertGreater(mock_fetch.call_count, 1)

            # 验证调用参数包含正确的日期格式
            for call in mock_fetch.call_args_list:
                data = call[0][1]  # 第二个参数是data
                self.assertIn('st', data)
                self.assertIn('et', data)
                self.assertIn('qqhs', data)
                self.assertIn('dwc', data)

    def test_get_deal_time_normal(self):
        """测试正常的时间格式转换"""
        result = self.account.get_deal_time('20250115', '143000')
        self.assertEqual(result, '2025-01-15 14:30:00')

    def test_get_deal_time_8_digit_time(self):
        """测试8位时间格式"""
        result = self.account.get_deal_time('20250115', '14300000')
        self.assertEqual(result, '2025-01-15 14:30:00')

    def test_get_deal_time_invalid_time(self):
        """测试无效时间格式"""
        result = self.account.get_deal_time('20250115', '1430')
        self.assertEqual(result, '2025-01-15 00:00')

        result = self.account.get_deal_time('20250115', '')
        self.assertEqual(result, '2025-01-15 00:00')


class TestAccountLoadHisDeals(unittest.TestCase):
    """测试 Account.load_his_deals 方法"""

    def setUp(self):
        self.account = Account()

    def test_load_his_deals_success(self):
        """测试成功加载历史交易"""
        mock_history_data = [
            {
                'Mmsm': '证券买入',
                'Zqdm': '600000',
                'Cjrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 100,
                'Cjjg': 12.50,
                'Wtbh': 'ORDER001',
                'Sxf': 5.0,
                'Yhs': 1.0,
                'Ghf': 2.0
            },
            {
                'Mmsm': '证券卖出',
                'Zqdm': '000001',
                'Cjrq': '20250115',
                'Cjsj': '150000',
                'Cjsl': 200,
                'Cjjg': 10.80,
                'Wtbh': 'ORDER002',
                'Sxf': 8.0,
                'Yhs': 2.0,
                'Ghf': 3.0
            }
        ]

        with patch.object(type(self.account), 'hisdeals_url', new_callable=lambda: property(lambda self: 'http://test.com/hisdeals')):
            with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
                with patch.object(self.account, '_upload_deals') as mock_upload:
                    self.account.load_his_deals('2025-01-01')

                    # 验证调用了_upload_deals
                    mock_upload.assert_called_once()

                    # 验证上传的数据格式
                    uploaded_deals = mock_upload.call_args[0][0]
                    uploaded_deals = list(uploaded_deals)  # 转换reversed对象

                    self.assertEqual(len(uploaded_deals), 2)

                    # 验证第一个交易记录
                    deal1 = uploaded_deals[1]  # reversed后的第一个
                    self.assertEqual(deal1['code'], '600000')
                    self.assertEqual(deal1['tradeType'], 'B')
                    self.assertEqual(deal1['price'], 12.50)
                    self.assertEqual(deal1['count'], 100)
                    self.assertEqual(deal1['time'], '2025-01-15 14:30:00')
                    self.assertEqual(deal1['fee'], 5.0)

    def test_load_his_deals_unknown_trade_type(self):
        """测试未知交易类型"""
        mock_history_data = [
            {
                'Mmsm': '未知交易类型',
                'Zqdm': '600000',
                'Cjrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 100,
                'Cjjg': 12.50,
                'Wtbh': 'ORDER001'
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                with patch('pyphon.accounts.logger') as mock_logger:
                    self.account.load_his_deals('2025-01-01')

                    # 应该记录日志
                    mock_logger.info.assert_called()

                    # 不应该上传任何数据
                    uploaded_deals = list(mock_upload.call_args[0][0])
                    self.assertEqual(len(uploaded_deals), 0)

    def test_load_his_deals_empty_code(self):
        """测试空股票代码"""
        mock_history_data = [
            {
                'Mmsm': '证券买入',
                'Zqdm': '',  # 空代码
                'Cjrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 100,
                'Cjjg': 12.50,
                'Wtbh': 'ORDER001'
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_his_deals('2025-01-01')

                # 不应该上传任何数据
                uploaded_deals = list(mock_upload.call_args[0][0])
                self.assertEqual(len(uploaded_deals), 0)

    def test_load_his_deals_zero_count(self):
        """测试零数量交易"""
        mock_history_data = [
            {
                'Mmsm': '证券买入',
                'Zqdm': '600000',
                'Cjrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 0,  # 零数量
                'Cjjg': 12.50,
                'Wtbh': 'ORDER001'
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                with patch('pyphon.accounts.logger') as mock_logger:
                    self.account.load_his_deals('2025-01-01')

                    # 应该记录日志
                    mock_logger.info.assert_called()

                    # 不应该上传任何数据
                    uploaded_deals = list(mock_upload.call_args[0][0])
                    self.assertEqual(len(uploaded_deals), 0)


class TestAccountLoadOtherDeals(unittest.TestCase):
    """测试 Account.load_other_deals 方法"""

    def setUp(self):
        self.account = Account()
        accld.jywg = Mock()
        accld.jywg.jywg = 'mock_domain'
        accld.jywg.validate_key = 'mock_key'

    def test_load_other_deals_dividend(self):
        """测试红利入账处理"""
        mock_history_data = [
            {
                'Ywsm': '红利入账',
                'Zqdm': '600000',
                'Ywrq': '20250115',
                'Cjsj': '000000',
                'Fsrq': '20250115',
                'Fssj': '150000',
                'Cjsl': 1,
                'Cjjg': 0,
                'Fsje': 100.0,
                'Htbh': 'DIV001',
                'Yhs': 0,
                'Ghf': 0
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_other_deals('2025-01-01')

                uploaded_deals = list(mock_upload.call_args[0][0])
                self.assertEqual(len(uploaded_deals), 1)

                deal = uploaded_deals[0]
                self.assertEqual(deal['tradeType'], '红利入账')
                self.assertEqual(deal['count'], 1)
                self.assertEqual(deal['price'], 100.0)
                self.assertEqual(deal['time'], '2025-01-15 15:00:00')

    def test_load_other_deals_stock_transfer_in(self):
        """测试股份转入处理"""
        mock_history_data = [
            {
                'Ywsm': '股份转入',
                'Zqdm': '600000',
                'Ywrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 100,
                'Cjjg': 12.50,
                'Htbh': 'TRANS001',
                'Yhs': 0,
                'Ghf': 0
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_other_deals('2025-01-01')

                uploaded_deals = list(mock_upload.call_args[0][0])
                self.assertEqual(len(uploaded_deals), 1)

                deal = uploaded_deals[0]
                self.assertEqual(deal['tradeType'], 'B')
                self.assertEqual(deal['count'], 100)
                self.assertEqual(deal['price'], 12.50)

    def test_load_other_deals_margin_interest(self):
        """测试融资利息处理和合并"""
        mock_history_data = [
            {
                'Ywsm': '偿还融资利息',
                'Zqdm': '600000',
                'Ywrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 1,
                'Cjjg': 0,
                'Fsje': 50.0,
                'Htbh': 'INT001',
                'Yhs': 0,
                'Ghf': 0
            },
            {
                'Ywsm': '偿还融资利息',
                'Zqdm': '600000',
                'Ywrq': '20250115',
                'Cjsj': '143000',  # 相同时间
                'Cjsl': 1,
                'Cjjg': 0,
                'Fsje': 30.0,
                'Htbh': 'INT002',
                'Yhs': 0,
                'Ghf': 0
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_other_deals('2025-01-01')

                uploaded_deals = list(mock_upload.call_args[0][0])
                # 应该合并为一条记录
                self.assertEqual(len(uploaded_deals), 1)

                deal = uploaded_deals[0]
                self.assertEqual(deal['tradeType'], '融资利息')
                self.assertEqual(deal['price'], 80.0)  # 50 + 30

    def test_load_other_deals_ignored_types(self):
        """测试忽略的交易类型"""
        mock_history_data = [
            {
                'Ywsm': '融资买入',  # 应该被忽略
                'Zqdm': '600000',
                'Ywrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 100,
                'Cjjg': 12.50,
                'Htbh': 'IGN001'
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_other_deals('2025-01-01')

                uploaded_deals = list(mock_upload.call_args[0][0])
                self.assertEqual(len(uploaded_deals), 0)

    def test_load_other_deals_empty_code(self):
        """测试空股票代码"""
        mock_history_data = [
            {
                'Ywsm': '红利入账',
                'Zqdm': '',  # 空代码
                'Ywrq': '20250115',
                'Cjsj': '143000',
                'Cjsl': 1,
                'Fsje': 100.0,
                'Htbh': 'DIV001'
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_other_deals('2025-01-01')

                uploaded_deals = list(mock_upload.call_args[0][0])
                self.assertEqual(len(uploaded_deals), 0)

    def test_merge_cum_deals(self):
        """测试合并相同时间的交易"""
        deals = [
            {'time': '2025-01-15 14:30:00', 'price': 50.0, 'code': '600000'},
            {'time': '2025-01-15 14:30:00', 'price': 30.0, 'code': '600000'},
            {'time': '2025-01-15 15:00:00', 'price': 20.0, 'code': '600000'}
        ]

        result = self.account.merge_cum_deals(deals)

        self.assertEqual(len(result), 2)
        # 找到14:30:00的记录
        deal_1430 = next(d for d in result if d['time'] == '2025-01-15 14:30:00')
        self.assertEqual(deal_1430['price'], 80.0)  # 50 + 30


class TestAccountTrade(unittest.TestCase):
    """测试 Account.trade 方法"""

    def setUp(self):
        self.account = Account()
        accld.jywg = Mock()
        accld.jywg.jywg = 'mock_domain'
        accld.jywg.validate_key = 'mock_key'
        self.account.available_money = 10000.0
        self.account.trading_records = []

    def test_trade_insufficient_money(self):
        """测试资金不足的情况"""
        self.account.available_money = 500.0  # 不足1000

        with patch('pyphon.accounts.logger') as mock_logger:
            result = self.account.trade('600000', 10.0, 100, 'B')

            self.assertIsNone(result)
            mock_logger.error.assert_called()

    def test_trade_invalid_count(self):
        """测试无效数量"""
        with patch('pyphon.accounts.logger') as mock_logger:
            result = self.account.trade('600000', 10.0, 0, 'B')

            self.assertIsNone(result)
            mock_logger.error.assert_called()

    @patch('pyphon.accounts.get_rt_price')
    def test_trade_zero_price_buy(self, mock_get_rt_price):
        """测试价格为0时的买入处理"""
        mock_get_rt_price.return_value = {
            'price': 10.0,
            'ask5': 10.5,
            'top_price': 11.0,
            'bid5': 9.5,
            'bottom_price': 9.0
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'get_form_data', return_value={}):
            self.account.trade('600000', 0, 100, 'B')

            # 验证使用了ask5价格
            mock_get_rt_price.assert_called_once_with('600000')

    @patch('pyphon.accounts.get_rt_price')
    def test_trade_zero_price_sell(self, mock_get_rt_price):
        """测试价格为0时的卖出处理"""
        mock_get_rt_price.return_value = {
            'price': 10.0,
            'ask5': 10.5,
            'top_price': 11.0,
            'bid5': 9.5,
            'bottom_price': 9.0
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'get_form_data', return_value={}):
            self.account.trade('600000', 0, 100, 'S')

            # 验证使用了bid5价格
            mock_get_rt_price.assert_called_once_with('600000')

    def test_trade_small_count_adjustment(self):
        """测试小数量时的调整逻辑"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'fetch_available_count', return_value=500):
            with patch.object(self.account, 'get_form_data', return_value={}):
                self.account.trade('600000', 10.0, 5, 'B')  # 小于10的数量

                # 应该调用fetch_available_count
                self.account.fetch_available_count.assert_called_once()

    def test_trade_success_buy(self):
        """测试成功的买入交易"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'get_form_data', return_value={}):
            self.account.trade('600000', 10.0, 100, 'B')

            # 验证资金减少
            self.assertEqual(self.account.available_money, 9000.0)  # 10000 - 10*100

            # 验证交易记录添加
            self.assertEqual(len(self.account.trading_records), 1)
            record = self.account.trading_records[0]
            self.assertEqual(record['code'], '600000')
            self.assertEqual(record['type'], 'B')
            self.assertEqual(record['sid'], 'ORDER001')

    def test_trade_success_sell(self):
        """测试成功的卖出交易"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER002', 'Wtrq': '20250115', 'Wtsj': '150000'}]
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'get_form_data', return_value={}):
            self.account.trade('600000', 10.0, 100, 'S')

            # 验证资金增加
            self.assertEqual(self.account.available_money, 11000.0)  # 10000 + 10*100

            # 验证交易记录添加
            self.assertEqual(len(self.account.trading_records), 1)
            record = self.account.trading_records[0]
            self.assertEqual(record['type'], 'S')

    def test_trade_api_error(self):
        """测试API返回错误"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 1,  # 错误状态
                'Message': 'Trade failed',
                'Data': []
            }
        }
        self.account.jysession.post.return_value = mock_response

        with patch.object(self.account, 'get_form_data', return_value={}):
            with patch('pyphon.accounts.logger') as mock_logger:
                self.account.trade('600000', 10.0, 100, 'B')

                # 应该记录错误日志
                mock_logger.error.assert_called()

                # 资金不应该变化
                self.assertEqual(self.account.available_money, 10000.0)

                # 不应该添加交易记录
                self.assertEqual(len(self.account.trading_records), 0)

    def test_trade_network_exception(self):
        """测试网络异常"""
        self.account.jysession.post.side_effect = Exception('Network error')

        with patch.object(self.account, 'get_form_data', return_value={}):
            with patch('pyphon.accounts.logger') as mock_logger:
                self.account.trade('600000', 10.0, 100, 'B')

                # 应该记录错误日志
                mock_logger.error.assert_called()

                # 资金不应该变化
                self.assertEqual(self.account.available_money, 10000.0)


class TestTrackingAccountMethods(unittest.TestCase):
    """测试 TrackingAccount 类的特定方法"""

    def setUp(self):
        self.account = TrackingAccount('test_track')

    @patch('pyphon.accounts.datetime')
    def test_tracking_account_trade_success(self, mock_datetime):
        """测试跟踪账户的成功交易"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15 14:30:00'

        # 先添加一个股票
        self.account.add_watch_stock('600000', {})

        self.account.trade('600000', 10.0, 100, 'B')

        # 验证持仓更新
        stock = self.account.get_stock('600000')
        self.assertEqual(stock['holdCount'], 100)

        # 验证交易记录
        self.assertEqual(len(self.account.trading_records), 1)
        record = self.account.trading_records[0]
        self.assertEqual(record['code'], '600000')
        self.assertEqual(record['type'], 'B')
        self.assertEqual(record['count'], 100)

    @patch('pyphon.accounts.datetime')
    def test_tracking_account_sell_without_stock(self, mock_datetime):
        """测试跟踪账户卖出不存在的股票"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15 14:30:00'

        with patch('pyphon.accounts.logger') as mock_logger:
            self.account.trade('600000', 10.0, 100, 'S')

            # 应该记录错误日志
            mock_logger.error.assert_called()

            # 不应该添加交易记录
            self.assertEqual(len(self.account.trading_records), 0)

    @patch('pyphon.accounts.datetime')
    def test_tracking_account_oversell(self, mock_datetime):
        """测试跟踪账户卖出超过持仓"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15 14:30:00'

        # 先买入100股
        self.account.add_watch_stock('600000', {})
        self.account.trade('600000', 10.0, 100, 'B')

        with patch('pyphon.accounts.logger') as mock_logger:
            # 尝试卖出200股
            self.account.trade('600000', 10.0, 200, 'S')

            # 应该记录错误日志
            mock_logger.error.assert_called()

            # 持仓不应该变化
            stock = self.account.get_stock('600000')
            self.assertEqual(stock['holdCount'], 100)

    @patch('pyphon.accounts.datetime')
    def test_tracking_account_duplicate_trade(self, mock_datetime):
        """测试跟踪账户重复交易"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15 14:30:00'

        self.account.add_watch_stock('600000', {})

        # 第一次交易
        self.account.trade('600000', 10.0, 100, 'B')

        with patch('pyphon.accounts.logger') as mock_logger:
            # 相同参数的第二次交易
            self.account.trade('600000', 10.0, 100, 'B')

            # 应该记录错误日志
            mock_logger.error.assert_called()

            # 应该只有一条交易记录
            self.assertEqual(len(self.account.trading_records), 1)

    def test_tracking_account_check_orders(self):
        """测试跟踪账户的check_orders方法"""
        # 添加一些交易记录
        self.account.trading_records = [
            {
                'code': '600000',
                'price': 10.0,
                'count': 100,
                'time': '2025-01-15 14:30:00',
                'sid': 1000,
                'type': 'B'
            }
        ]

        with patch.object(self.account, 'extend_stock_buydetail') as mock_extend:
            result = self.account.check_orders()

            # 验证返回结果
            self.assertIn('600000', result)
            self.assertEqual(len(result['600000']), 1)

            deal = result['600000'][0]
            self.assertEqual(deal['code'], '600000')
            self.assertEqual(deal['type'], 'B')
            self.assertEqual(deal['date'], '2025-01-15 14:30:00')

            # 验证调用了extend_stock_buydetail
            mock_extend.assert_called_once()


if __name__ == '__main__':
    unittest.main()
    # suite = unittest.TestSuite()
    # suite.addTest(TestAccountLoadOtherDeals('test_merge_cum_deals'))
    # unittest.TextTestRunner().run(suite)
