import logging
import os
import base64
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, HTTPException, Body, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel, Field
from config import Config
from log import logger
from jywg import jywg
from accounts import accld
from timers import alarm_hub


# 将FastAPI相关的日志重定向到自定义logger
for logger_name in ["fastapi", "uvicorn", "uvicorn.access","uvicorn.error"]:
    log = logging.getLogger(logger_name)
    log.handlers.clear()
    log.setLevel(logger.level)
    log.propagate = False
    for h in logger.handlers:
        log.addHandler(h)


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

class TradeRequest(BaseModel):
    # 根据实际需求定义交易请求的字段
    code: str  # 股票代码，必填
    action: str  # 买入或卖出，必填
    price: float  # 价格，必填
    quantity: int  # 数量，必填
    order_type: str = "limit"  # 订单类型，可选，默认为"limit"
    remark: Optional[str] = None  # 备注，可选
    timeout: Optional[int] = Field(
        default=60,
        description="订单超时时间（秒）",
        ge=10,  # 大于等于10
        le=300  # 小于等于300
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
        if alarm_hub.delay_seconds('15:00') <= 0:
            logger.info("已收盘，不设置定时任务")
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
            if alarm_hub.delay_seconds(task['end']) < 3*60*60:
                alarm_hub.cancel_task(task['id'])

    def start(self):
        self.running = True
        if self.jywg:
            if self.jywg.validate():
                self.on_login_success()

    def on_login_success(self):
        self.status = 'success'
        accld.jywg = self.jywg
        acc = Config.account()
        fha = Config.data_service()
        bearer = base64.b64encode((fha['uemail'] + ":" + Config.simple_decrypt(fha['pwd'])).encode()).decode()
        fha['headers'] = {'Authorization': f'Basic {bearer}'}
        accld.enable_credit = acc['credit']
        accld.fha = fha
        accld.load_accounts()
        accld.normal_account.load_assets()
        if acc['credit']:
            accld.collateral_account.load_assets()
        # accld.init_track_accounts()
        # # costDog.init()
        alarm_hub.purchase_new_stocks = tconfig['purchase_new_stocks']
        alarm_hub.on_trade_closed = self.on_trade_closed
        alarm_hub.setup_alarms()

    def on_trade_closed(self):
        self.running = False
        self.status = "closed"
        logger.info("交易系统已关闭")

    def handleStatus(self):
        # 返回交易系统状态
        return {"status": "ok" if self.running else "stopped"}

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
        logger.info(f"处理交易请求: {trade_data}")
        return True

    def handleAccountStocks(self, query_params):
        # 获取账户股票信息
        return {"stocks": []}

    def handleAccountDeals(self, query_params):
        # 获取账户交易记录
        return {"deals": []}

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
    r = ext.handleStatus()
    return r

@app.get("/start")
async def start():
    s = ext.handleStart()
    return s

@app.post("/trade")
async def trade(request: Request):
    trade_data = await request.json()
    if ext.handleTrade(trade_data):
        return {"message": "Success"}
    raise HTTPException(status_code=404, detail="Trade type not found!")

@app.get("/stocks")
async def stocks(request: Request):
    query_params = dict(request.query_params)
    return ext.handleAccountStocks(query_params)

@app.get("/deals")
async def deals(request: Request):
    query_params = dict(request.query_params)
    return ext.handleAccountDeals(query_params)

@app.get("/iunstrs")
async def iunstrs():
    return tconfig.get('iunstrs', {})

@app.get("/rzrq")
async def rzrq(code: str = Query(None)):
    if not ext.running:
        return False
    rzrq_result = await accld.check_rzrq(code)
    return rzrq_result.get("Status") != -1

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
