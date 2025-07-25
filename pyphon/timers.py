import random
from datetime import datetime
from threading import Timer
from log import logger
from accounts import accld


class alarm_hub:
    timers = []
    last_tid = 0
    purchase_new_stocks = False
    on_trade_closed = None

    @staticmethod
    def delay_seconds(daytime:str)->float:
        '''计算当前时间到daytime的时间间隔'''
        dnow = datetime.now()
        dtarr = daytime.split(':')
        hr = int(dtarr[0])
        minutes = 0 if len(dtarr) < 2 else int(dtarr[1])
        secs = 0 if len(dtarr) < 3 else int(dtarr[2])
        target_time = dnow.replace(hour=hr, minute=minutes, second=secs)
        return (target_time - dnow).total_seconds()

    @classmethod
    def add_timer_task(self, callback, target_time, end_time=None) -> int:
        seconds_until = self.delay_seconds(target_time)
        if seconds_until < 0:
            if end_time is None or self.delay_seconds(end_time) < 0:
                return
            seconds_until = 0.1

        timer = Timer(seconds_until, callback)
        timer.daemon = True
        timer.start()
        tid = self.last_tid + 1
        self.timers.append({'id': tid, 'timer': timer})
        logger.info(f"已设置定时任务{callback.__name__}，将在 {target_time} 执行")
        return tid

    @classmethod
    def cancel_task(self, tid):
        t = next((t for t in self.timers if t['id'] == tid), None)
        if t:
            t['timer'].cancel()

    @classmethod
    def daily_routine_tasks(self):
        if self.purchase_new_stocks:
            accld.buy_new_stocks()
        accld.buy_new_bonds()

    @classmethod
    def before_trade_close(self):
        accld.normal_account.buy_fund_before_close()
        if accld.collateral_account:
            accld.collateral_account.buy_fund_before_close()

    @classmethod
    def trade_closed(self):
        """收盘后处理逻辑"""
        logger.info("交易日结束，执行收盘后处理")

        # 保存当日交易数据
        if hasattr(accld, 'normal_account') and accld.normal_account:
            try:
                accld.normal_account.load_deals()
                logger.info("已保存普通账户当日交易数据")
            except Exception as e:
                logger.error(f"保存普通账户交易数据失败: {str(e)}")

        # 如果有融资融券账户，也保存其交易数据
        if hasattr(accld, 'collateral_account') and accld.collateral_account:
            try:
                accld.collateral_account.load_deals()
                logger.info("已保存融资融券账户当日交易数据")
            except Exception as e:
                logger.error(f"保存融资融券账户交易数据失败: {str(e)}")

        # 更新状态
        if callable(self.on_trade_closed):
            self.on_trade_closed()

    @classmethod
    def setup_alarms(self):
        # checkorder task
        timerand = random.choice([f'9:{random.randint(40, 59)}', f'10:{random.randint(0, 40)}'])
        self.add_timer_task(self.daily_routine_tasks, timerand)
        self.add_timer_task(self.before_trade_close, '14:59:48')
        self.add_timer_task(self.trade_closed, '15:01')
