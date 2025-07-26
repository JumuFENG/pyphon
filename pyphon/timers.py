import random
from time import sleep
from threading import Timer
from log import logger
from accounts import accld
from misc import delay_seconds


class alarm_hub:
    timers = []
    last_tid = 0
    purchase_new_stocks = False
    on_trade_closed = None

    @classmethod
    def add_timer_task(self, callback, target_time, end_time=None) -> int:
        seconds_until = delay_seconds(target_time)
        if seconds_until < 0:
            if end_time is None or delay_seconds(end_time) < 0:
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
    def check_orders(self):
        short_seconds_wait = 600
        waiting_ids = []
        while True:
            accld.normal_account.check_orders()
            if accld.collateral_account:
                accld.collateral_account.check_orders()

            if delay_seconds('14:55') < 0:
                break

            seconds = 600
            if delay_seconds('11:00') < 0 and delay_seconds('13:00') > 0:
                seconds = delay_seconds('13:0:5')
            wids = []
            for r in accld.normal_account.trading_records:
                if r['sid'] not in waiting_ids:
                    wids.append(r['sid'])
            if accld.collateral_account:
                for r in accld.collateral_account.trading_records:
                    if r['sid'] not in waiting_ids:
                        wids.append(r['sid'])
            if len(wids) > 0:
                waiting_ids.extend(wids)
                short_seconds_wait = 5
            else:
                short_seconds_wait *= 2

            sleep(seconds = min(short_seconds_wait, seconds))

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
        """收盘后处理逻辑
        先执行一遍before close的国债逆回购和融资还款流程, 然后进行盘后处理
        """
        accld.normal_account.buy_fund_before_close()
        if accld.collateral_account:
            accld.repay_margin_loan()

        sleep(30)
        logger.info("交易日结束，执行收盘后处理")

        # 保存当日交易数据
        for acc in accld.all_accounts:
            deals = acc.load_deals()
            acc.archive_deals(deals)

        # 更新状态
        if callable(self.on_trade_closed):
            self.on_trade_closed()

    @classmethod
    def setup_alarms(self):
        accld.upload_every_monday()
        self.add_timer_task(self.check_orders, '9:30:10', '14:53')
        timerand = random.choice([f'9:{random.randint(40, 59)}', f'10:{random.randint(0, 40)}'])
        self.add_timer_task(self.daily_routine_tasks, timerand)
        self.add_timer_task(self.before_trade_close, '14:59:48')
        self.add_timer_task(self.trade_closed, '15:0:10')
