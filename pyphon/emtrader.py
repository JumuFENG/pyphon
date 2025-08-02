import os
import base64
from traceback import format_exc
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, HTTPException, Body, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel, Field
from lofig import logger, Config
from jywg import jywg
from accounts import accld
from timers import alarm_hub
from misc import is_today_trading_day, delay_seconds


# 获取配置
tconfig = Config.trade_config()
port = tconfig['port']

# 创建FastAPI应用
app = FastAPI(title="EMTrader API", description="Trading API for East Money Securities")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TradingExtension:
    def __init__(self):
        self.running = False
        self.status = None
        acc = Config.account()
        self.jywg = None
        if acc['account']:
            self.jywg = jywg(**acc, active_time=1800)
        else:
            logger.error('account not set in config file!')
        # 初始化定时器存储
        self.start_timers = []

    def schedule(self):
        """
        设置定时任务:
        - 当天9:12和12:45执行self.start (可以取消)
        - 如果当前时间超过预定时间则不执行
        """
        # 如果已经收盘，不设置任何任务
        if delay_seconds('15:00') <= 0:
            logger.info("已收盘，不设置定时任务")
            return

        if not is_today_trading_day():
            logger.info("今天不是交易日，不设置定时任务")
            return

        # 处理上午交易时段
        tid = alarm_hub.add_timer_task(self.start, '9:12', '11:30')
        if tid:
            self.start_timers.append({'id': tid, 'start': '9:12', 'end': '11:30'})
        # 处理下午交易时段
        tid = alarm_hub.add_timer_task(self.start, '12:45', '15:0')
        if tid:
            self.start_timers.append({'id': tid, 'start':'12:45', 'end': '15:0'})

    def cancel_pending_start_tasks(self):
        """取消当前时段内即将执行的启动任务"""
        if len(self.start_timers) == 0:
            return

        for task in self.start_timers:
            if delay_seconds(task['end']) < 3*60*60:
                alarm_hub.cancel_task(task['id'])

    def start(self):
        self.running = True
        if self.jywg:
            if self.jywg.validate():
                self.on_login_success()

    def on_login_success(self):
        self.status = 'success'
        if accld.jywg:
            return
        accld.jywg = self.jywg
        acc = Config.account()
        fha = Config.data_service()
        if 'pwd' in fha:
            bearer = base64.b64encode(f"{fha['uemail']}:{Config.simple_decrypt(fha['pwd'])}".encode()).decode()
            fha['headers'] = {'Authorization': f'Basic {bearer}'}
        accld.enable_credit = acc['credit']
        accld.fha = fha
        accld.load_accounts()
        accld.normal_account.load_assets()
        if acc['credit']:
            accld.collateral_account.load_assets()
        accld.init_track_accounts()
        # costDog.init()
        alarm_hub.purchase_new_stocks = tconfig['purchase_new_stocks']
        alarm_hub.on_trade_closed = self.on_trade_closed
        alarm_hub.setup_alarms()

    def on_trade_closed(self):
        self.running = False
        self.status = "closed"
        logger.info("已收盘")

    def handleStatus(self):
        # 返回交易状态
        return {
            "running": self.running,
            "status": self.status if self.status else ("running" if self.running else "stopped"),
            "accounts": list(accld.all_accounts.keys()) if accld.all_accounts else []
        }

    def handleStart(self):
        """启动交易系统并取消即将执行的自动启动任务"""
        self.running = True
        if self.jywg:
            if self.jywg.validate():
                self.on_login_success()
                # 取消即将执行的自动启动任务
                self.cancel_pending_start_tasks()
                return {"status": "started"}
            return {"status": "start error"}
        return {"status": "jywg not initialized!"}

    def handleTrade(self, trade_data):
        # 处理交易请求
        code = trade_data.get('code')
        tradeType = trade_data.get('tradeType')
        count = trade_data.get('count', 0)
        price = trade_data.get('price', 0)
        account = trade_data.get('account')
        strategies = trade_data.get('strategies')

        # 验证必填参数
        if not code or not tradeType:
            logger.error(f"Missing required parameters: code={code}, tradeType={tradeType}")
            return False

        if tradeType == 'B':
            if not account:
                # 买入时如果没有指定账户，自动选择
                rzrq = accld.check_rzrq(code)
                account = 'credit' if rzrq else 'normal'
                logger.info(f"Auto-selected account: {account} for code: {code}")
            accld.buy_stock(code, price, count, account, strategies)
        elif tradeType == 'S':
            if not account:
                logger.error("Account is required for sell orders")
                return False
            accld.sell_stock(code, price, count, account)
        elif strategies and code and account:
            # 仅添加监控股票
            accld.all_accounts[account].addWatchStock(code, strategies)
        else:
            logger.error(f"Invalid trade request: tradeType={tradeType}, code={code}, account={account}")
            return False
        return True

    def handleAccountStocks(self, account='normal'):
        # 获取账户股票信息
        if account not in accld.all_accounts:
            logger.error(f"Invalid account: {account}")
            return {"error": f"Invalid account: {account}", "stocks": []}

        try:
            stocks = []
            for s in accld.all_accounts[account].stocks:
                sobj = {k: v for k,v in s.items() if k not in ('buydetail', 'buydetail_full')}
                if s.get('buydetail', None) or s.get('buydetail_full', None):
                    if 'strategies' not in sobj or not sobj['strategies']:
                        sobj['strategies'] = {'buydetail': s['buydetail'], 'buydetail_full': s['buydetail_full']}
                    else:
                        sobj['strategies']['buydetail'] = s['buydetail']
                        sobj['strategies']['buydetail_full'] = s['buydetail_full']
                stocks.append(sobj)
            return {"account": account, "stocks": stocks}
        except Exception as e:
            logger.error(f"Error getting stocks for account {account}: {str(e)}")
            logger.debug(format_exc())
            return {"error": str(e), "stocks": []}

    def handleAccountDeals(self, account='normal'):
        # 获取账户当日交易记录
        if not self.running:
            logger.warning("Trading system is not running")
            if accld.all_accounts[account].today_deals:
                return {"account": account, "deals": accld.all_accounts[account].today_deals}
            return {"account": account, "deals": []}

        if account not in accld.all_accounts:
            logger.error(f"Invalid account: {account}")
            return {"error": f"Invalid account: {account}", "deals": []}

        try:
            deals = accld.all_accounts[account].check_orders()
            accld.all_accounts[account].today_deals = deals
            return {"account": account, "deals": deals}
        except Exception as e:
            logger.error(f"Error getting deals for account {account}: {str(e)}")
            logger.debug(format_exc())
            return {"error": str(e), "deals": []}


# 创建交易扩展实例
ext = TradingExtension()


# 静态文件目录
static_dir = os.path.join(os.path.dirname(__file__), 'web')
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    index_path = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to EMTrader API"}

@app.get("/status")
async def status():
    """获取交易系统状态"""
    try:
        return ext.handleStatus()
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/start")
async def start():
    """启动交易系统"""
    try:
        return ext.handleStart()
    except Exception as e:
        logger.error(f"Error starting system: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

class TradeRequest(BaseModel):
    # 根据实际需求定义交易请求的字段
    code: str = Field(..., description="股票代码，必填")
    tradeType: str = Field(..., description="交易类型：B(买入)或S(卖出)，必填")
    account: Optional[str] = Field(None, description="账户类型：normal, collateral, credit等，买入时可选")
    price: float = Field(0, description="价格，0表示市价")
    count: int = Field(0, description="数量")
    strategies: Optional[Dict[str, Any]] = Field(None, description="策略参数，可选")

@app.post("/trade")
async def trade(request: TradeRequest):
    try:
        if ext.handleTrade(request.model_dump()):
            return {"status": "success", "message": "Trade executed successfully"}
        else:
            raise HTTPException(status_code=400, detail="Trade execution failed")
    except Exception as e:
        logger.error("Trade error: %s %s", e, request.model_dump())
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/stocks")
async def stocks(account: str = Query('normal', description="账户类型: normal, collateral, credit, track")):
    """获取指定账户的股票持仓信息"""
    try:
        return ext.handleAccountStocks(account)
    except Exception as e:
        logger.error(f"Error in /stocks endpoint: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/deals")
async def deals(account: str = Query('normal', description="账户类型: normal, collateral, credit, track")):
    """获取指定账户的交易记录"""
    try:
        return ext.handleAccountDeals(account)
    except Exception as e:
        logger.error(f"Error in /deals endpoint: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/iunstrs")
async def iunstrs():
    """获取配置的iunstrs信息"""
    try:
        return tconfig.get('iunstrs', {})
    except Exception as e:
        logger.error(f"Error getting iunstrs: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/rzrq")
async def rzrq(code: str = Query(..., description="股票代码，必填")):
    """检查股票是否支持融资融券"""
    try:
        if not ext.running:
            return False

        if not code:
            raise HTTPException(status_code=400, detail="Stock code is required")

        return accld.check_rzrq(code)
    except Exception as e:
        logger.error(f"Error checking rzrq for code {code}: {str(e)}")
        logger.debug(format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def start_server():
    # 设置定时任务
    ext.schedule()

    # 启动服务器 - 禁用uvicorn的默认日志配置，使用我们的自定义logger
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None,  # 禁用默认日志配置
        access_log=True
    )


if __name__ == "__main__":
    start_server()
