#!/usr/bin/env python3
"""
测试 pyphon/accounts.py 中具体账户类的接口方法
专门测试：check_orders, archive_deals, get_history_deals, load_his_deals, load_other_deals, trade
HTTP请求需要mock，其它尽量不要mock
"""

import unittest
import sys
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pyphon'))

from pyphon.accounts import NormalAccount, CollateralAccount, TrackingAccount


class TestNormalAccountCheckOrders(unittest.TestCase):
    """测试 NormalAccount.check_orders 方法"""

    def setUp(self):
        self.account = NormalAccount()
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


class TestNormalAccountArchiveDeals(unittest.TestCase):
    """测试 NormalAccount.archive_deals 方法"""

    def setUp(self):
        self.account = NormalAccount()
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


class TestNormalAccountGetHistoryDeals(unittest.TestCase):
    """测试 NormalAccount.get_history_deals 方法"""

    def setUp(self):
        self.account = NormalAccount()

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.accld')
    def test_get_history_deals_string_date(self, mock_accld, mock_datetime):
        """测试字符串日期输入"""
        mock_datetime.now.return_value = datetime(2025, 1, 15)
        mock_datetime.strptime = datetime.strptime

        # Mock accld.jywg.session
        mock_session = Mock()
        mock_accld.jywg.session = mock_session

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.json.return_value = {
            'Status': 0,
            'Data': [{'order_id': '001', 'Dwc': 'a'}, {'order_id': '002', 'Dwc': ''}]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        result = self.account.get_history_deals('http://test.com', '2024-12-01')

        # 应该调用HTTP请求
        self.assertTrue(mock_session.post.called)
        # 返回结果应该包含所有数据
        self.assertEqual(len(result), 2)

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.accld')
    def test_get_history_deals_date_sections(self, mock_accld, mock_datetime):
        """测试日期分段逻辑"""
        mock_datetime.now.return_value = datetime(2025, 1, 15)
        mock_datetime.strptime = datetime.strptime

        # Mock accld.jywg.session
        mock_session = Mock()
        mock_accld.jywg.session = mock_session

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.json.return_value = {
            'Status': 0,
            'Data': []
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        # 测试跨度超过90天的日期范围
        self.account.get_history_deals('http://test.com', '2024-10-01')

        # 应该被分成多个时间段调用
        self.assertGreater(mock_session.post.call_count, 1)


class TestNormalAccountLoadHisDeals(unittest.TestCase):
    """测试 NormalAccount.load_his_deals 方法"""

    def setUp(self):
        self.account = NormalAccount()

    @patch('pyphon.accounts.accld')
    def test_load_his_deals_success(self, mock_accld):
        """测试成功加载历史交易"""
        # Mock accld properties
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

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
            }
        ]

        with patch.object(self.account, 'get_history_deals', return_value=mock_history_data):
            with patch.object(self.account, '_upload_deals') as mock_upload:
                self.account.load_his_deals('2025-01-01')

                # 验证调用了_upload_deals
                mock_upload.assert_called_once()

                # 验证上传的数据格式
                uploaded_deals = mock_upload.call_args[0][0]
                uploaded_deals = list(uploaded_deals)  # 转换reversed对象

                self.assertEqual(len(uploaded_deals), 1)

                # 验证交易记录
                deal = uploaded_deals[0]
                self.assertEqual(deal['code'], '600000')
                self.assertEqual(deal['tradeType'], 'B')
                self.assertEqual(deal['price'], 12.50)
                self.assertEqual(deal['count'], 100)
                self.assertEqual(deal['time'], '2025-01-15 14:30:00')
                self.assertEqual(deal['fee'], 5.0)

    @patch('pyphon.accounts.accld')
    def test_load_his_deals_unknown_trade_type(self, mock_accld):
        """测试未知交易类型"""
        # Mock accld properties
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

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


class TestNormalAccountLoadOtherDeals(unittest.TestCase):
    """测试 NormalAccount.load_other_deals 方法"""

    def setUp(self):
        self.account = NormalAccount()

    @patch('pyphon.accounts.accld')
    def test_load_other_deals_dividend(self, mock_accld):
        """测试红利入账处理"""
        # Mock accld properties
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

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

    @patch('pyphon.accounts.accld')
    def test_load_other_deals_ignored_types(self, mock_accld):
        """测试忽略的交易类型"""
        # Mock accld properties
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

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


class TestNormalAccountTrade(unittest.TestCase):
    """测试 NormalAccount.trade 方法"""

    def setUp(self):
        self.account = NormalAccount()
        self.account.available_money = 10000.0
        self.account.trading_records = []

    @patch('pyphon.accounts.accld')
    @patch('pyphon.accounts.get_rt_price')
    def test_trade_success_buy(self, mock_get_rt_price, mock_accld):
        """测试成功的买入交易"""
        # Mock accld
        mock_session = Mock()
        mock_accld.jywg.session = mock_session
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        self.account.trade('600000', 10.0, 100, 'B')

        # 验证资金减少
        self.assertEqual(self.account.available_money, 9000.0)  # 10000 - 10*100

        # 验证交易记录添加
        self.assertEqual(len(self.account.trading_records), 1)
        record = self.account.trading_records[0]
        self.assertEqual(record['code'], '600000')
        self.assertEqual(record['type'], 'B')
        self.assertEqual(record['sid'], 'ORDER001')

    @patch('pyphon.accounts.accld')
    def test_trade_insufficient_money(self, mock_accld):
        """测试资金不足的情况"""
        self.account.available_money = 500.0  # 不足1000

        with patch('pyphon.accounts.logger') as mock_logger:
            result = self.account.trade('600000', 10.0, 100, 'B')

            self.assertIsNone(result)
            mock_logger.error.assert_called()

    @patch('pyphon.accounts.accld')
    def test_trade_api_error(self, mock_accld):
        """测试API返回错误"""
        # Mock accld
        mock_session = Mock()
        mock_accld.jywg.session = mock_session
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 1,  # 错误状态
                'Message': 'Trade failed',
                'Data': []
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        with patch('pyphon.accounts.logger') as mock_logger:
            self.account.trade('600000', 10.0, 100, 'B')

            # 应该记录错误日志
            mock_logger.error.assert_called()

            # 资金不应该变化
            self.assertEqual(self.account.available_money, 10000.0)

            # 不应该添加交易记录
            self.assertEqual(len(self.account.trading_records), 0)


class TestCollateralAccountMethods(unittest.TestCase):
    """测试 CollateralAccount 的特定方法"""

    def setUp(self):
        self.account = CollateralAccount()
        self.account.available_money = 10000.0
        self.account.trading_records = []

    @patch('pyphon.accounts.datetime')
    @patch('pyphon.accounts.delay_seconds')
    def test_check_orders_success_deals(self, mock_delay_seconds, mock_datetime):
        """测试融资融券账户的订单检查"""
        mock_datetime.now.return_value.strftime.return_value = '2025-01-15'
        mock_delay_seconds.return_value = -3600  # 已过15:00

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

                # 验证返回结果
                self.assertIn('600000', result)
                self.assertEqual(len(result['600000']), 1)

                buy_deal = result['600000'][0]
                self.assertEqual(buy_deal['code'], '600000')
                self.assertEqual(buy_deal['type'], 'B')

    @patch('pyphon.accounts.accld')
    def test_trade_success_buy(self, mock_accld):
        """测试融资融券账户的成功买入交易"""
        # Mock accld
        mock_session = Mock()
        mock_accld.jywg.session = mock_session
        mock_accld.jywg.jywg = 'http://test.com'
        mock_accld.jywg.validate_key = 'test_key'

        # Mock HTTP响应
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': {
                'Status': 0,
                'Data': [{'Wtbh': 'ORDER001', 'Wtrq': '20250115', 'Wtsj': '143000'}]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        self.account.trade('600000', 10.0, 100, 'B')

        # 验证资金减少
        self.assertEqual(self.account.available_money, 9000.0)

        # 验证交易记录添加
        self.assertEqual(len(self.account.trading_records), 1)
        record = self.account.trading_records[0]
        self.assertEqual(record['code'], '600000')
        self.assertEqual(record['type'], 'B')


if __name__ == '__main__':
    # unittest.main()
    suite = unittest.TestSuite()
    suite.addTest(TestNormalAccountGetHistoryDeals('test_get_history_deals_string_date'))
    unittest.TextTestRunner().run(suite)
