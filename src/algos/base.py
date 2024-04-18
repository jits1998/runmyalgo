import asyncio
import datetime
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Type

import psycopg2  # type: ignore

import instruments
from broker import tickers
from broker.base import Broker, Ticker
from config import get_server_config
from core.strategy import BaseStrategy, StartTimedBaseStrategy
from exceptions import DeRegisterStrategyException
from instruments import symbol_to_CMP as cmp
from models import (
    AlgoStatus,
    Direction,
    OrderType,
    ProductType,
    TickData,
    TradeState,
    UserDetails,
)
from models.order import Order
from models.trade import Trade
from utils import (
    get_today_date_str,
    get_user_details,
    is_market_closed_for_the_day,
    is_today_holiday,
)


class BaseAlgo(threading.Thread, ABC):
    access_token: str
    short_code: str
    user_details: UserDetails
    broker: Broker
    ticker: Ticker
    loop: asyncio.AbstractEventLoop

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None) -> None:
        super(BaseAlgo, self).__init__(group=group, target=target, name=name)
        (
            self.access_token,
            self.short_code,
            self.multiple,
        ) = args
        self.loop = asyncio.new_event_loop()
        self.tasks: List = []
        self.registered_symbols: List[str] = []
        asyncio.set_event_loop(self.loop)
        self.trades_queue: asyncio.Queue[Trade] = asyncio.Queue()
        self.orders_queue: asyncio.Queue[Order] = asyncio.Queue()

        self.loop.set_debug(True)
        self.questDBCursor = self.get_questdb_connection()
        self.strategies_data: Dict[str, Any] = {}
        self.trades: List[Trade] = []
        self.orders: Dict[str, Order] = {}
        self.strategy_to_instance: Dict[str, BaseStrategy] = {}
        self.status = AlgoStatus.INITIATED

    def run(self) -> None:
        self.loop.run_forever()

    def start_algo(self):

        logging.info("Starting Algo...")

        all_instruments = instruments.fetch_instruments(self.short_code, self.broker)

        if len(all_instruments) == 0:
            # something is wrong. We need to inform the user
            logging.warn("Algo not started.")
            return

        self.symbol_to_cmp = cmp[self.short_code]

        server_config = get_server_config()
        trades_dir = os.path.join(server_config["deploy_dir"], "trades")
        self.intradayTradesDir = os.path.join(trades_dir, get_today_date_str())
        if os.path.exists(self.intradayTradesDir) == False:
            logging.info("TradeManager: Intraday Trades Directory %s does not exist. Hence going to create.", self.intradayTradesDir)
            os.makedirs(self.intradayTradesDir)

        self.ticker = tickers[get_user_details(self.short_code).broker_name](self.short_code, self.broker)

        self.ticker.start_ticker()
        self.ticker.register_listener(self.ticker_listener)

        self.ticker.register_symbols(["NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY FIN SERVICE"])

        # Load all trades from json files to app memory
        self.load_trades_from_file()
        self.load_strategies_from_file()

        while len(self.symbol_to_cmp) < 4:
            time.sleep(2)

        play_task = asyncio.run_coroutine_threadsafe(self.play(), self.loop)
        play_task.add_done_callback(self.handle_exception)
        self.tasks.append(play_task)

        orders_task = asyncio.run_coroutine_threadsafe(self.add_orders(), self.loop)
        orders_task.add_done_callback(self.handle_exception)
        self.tasks.append(orders_task)
        self.broker.orders_queue = self.orders_queue

        trades_task = asyncio.run_coroutine_threadsafe(self.add_trades(), self.loop)
        trades_task.add_done_callback(self.handle_exception)
        self.tasks.append(trades_task)
        self.broker.trades_queue = self.trades_queue

        start_strategies_fut = asyncio.run_coroutine_threadsafe(self.start_strategies(self.short_code, self.multiple), self.loop)
        start_strategies_fut.add_done_callback(self.handle_exception)
        self.tasks.append(start_strategies_fut)

        self.status = AlgoStatus.STARTED

        logging.info("Algo started.")

    async def play(self):  # track and update trades in a loop
        while True:

            if self.questDBCursor is None or self.questDBCursor.closed:
                self.questDBCursor = self.get_questdb_connection()

            if not is_today_holiday() and not is_market_closed_for_the_day() and not len(self.strategy_to_instance) == 0:

                # save updated data to json file
                self.save_trades_to_file()
                self.save_strategies_to_file()
                self.broker.fetch_update_all_orders(self.orders)

            now = datetime.datetime.now()
            waitSeconds = 30 - (now.second % 30)
            await asyncio.sleep(waitSeconds)

    @abstractmethod
    async def start_strategies(self, short_code, multiple=0): ...

    async def start_strategy(self, strategy: Type[BaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        strategy_instance = strategy(short_code, self.broker, multiple)  # type: ignore
        self._start_strategy(strategy_instance, run)

    async def start_timed_strategy(
        self, strategy: Type[StartTimedBaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None
    ):
        strategy_instance = strategy(short_code, startTimestamp, self.broker, multiple)
        self._start_strategy(strategy_instance, run)

    def _start_strategy(self, strategy_instance: BaseStrategy, run):
        strategy_instance.trades = self.get_trades_by_strategy(strategy_instance.getName())
        strategy_instance.run_config = run

        strategy_task = asyncio.create_task(strategy_instance.run())
        strategy_task.set_name(strategy_instance.getName())
        strategy_task.add_done_callback(self.handle_exception)

        self.tasks.append(strategy_task)
        self.register_strategy(strategy_instance)

    def handle_exception(self, task):
        if task.exception() is not None:
            logging.info("Exception in %s", task.get_name())
            logging.info(task.exception())
            if isinstance(task.exception(), DeRegisterStrategyException):
                self.dergister_strategy(task.get_name())
                pass

    async def add_orders(self) -> None:
        while True:
            order: Order = await self.orders_queue.get()
            self.orders[order.order_id] = order

    async def add_trades(self) -> None:
        while True:
            trade: Trade = await self.trades_queue.get()
            self.trades.append(trade)

    def ticker_listener(self, tick) -> None:
        if isinstance(tick, TickData):
            # assert isinstance(tick, TickData)
            tick_data: TickData = tick
            logging.debug("tickerLister: new tick received for %s = %f", tick_data.trading_symbol, tick_data.lastTradedPrice)
            # Store the latest tick in map
            self.symbol_to_cmp[tick.trading_symbol] = tick.lastTradedPrice
            if tick.exchange_timestamp:
                self.symbol_to_cmp["exchange_timestamp"] = tick.exchange_timestamp
        elif "orderReference" in tick:
            tick_order_id = tick["orderReference"]
            if tick_order_id in self.orders:
                self.broker.handle_order_update_tick(self.orders[tick_order_id], tick)

    def get_trades_by_strategy(self, strategy: str) -> List[Trade]:
        tradesByStrategy = []
        for trade in self.trades:
            if trade.strategy == strategy:
                tradesByStrategy.append(trade)
        return tradesByStrategy

    def register_strategy(self, strategy_instance):
        self.strategy_to_instance[strategy_instance.getName()] = strategy_instance
        strategy_instance.strategyData = self.strategies_data.get(strategy_instance.getName(), None)

    def dergister_strategy(self, strategy_name):
        del self.strategy_to_instance[strategy_name]

    def get_questdb_connection(self):
        try:
            connection = psycopg2.connect(user="admin", password="quest", host="127.0.0.1", port="8812", database="qdb")
            cursor = connection.cursor()

            cursor.execute(
                """CREATE TABLE IF NOT EXISTS {0} ( ts TIMESTAMP, strategy string, trading_symbol string, tradeId string, cmp float, entry float, pnl float, qty int, status string) timestamp(ts) partition by year""".format(
                    self.short_code
                )
            )
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS {0}_tickData( ts TIMESTAMP, trading_symbol string, ltp float, qty int, avgPrice float, volume int, totalBuyQuantity int, totalSellQuantity int, open float, high float, low float, close float, change float) timestamp(ts) partition by year""".format(
                    self.short_code
                )
            )

            logging.info("Connected to Quest DB")
            return cursor
        except Exception as err:
            logging.info("Can't connect to QuestDB")
            return None

    def load_trades_from_file(self):
        trades_filepath = self.get_trades_filepath()
        if os.path.exists(trades_filepath) == False:
            logging.warn("TradeManager: load_trades_from_file() Trades Filepath %s does not exist", trades_filepath)
            return
        self.trades = []
        tFile = open(trades_filepath, "r")
        tradesData = json.loads(tFile.read())
        for tr in tradesData:
            trade = convert_json_to_trade(tr)
            logging.info("load_trades_from_file trade => %s", trade)
            self.trades.append(trade)
            if trade.trading_symbol not in self.registered_symbols:
                # Algo register symbols with ticker
                self.ticker.register_symbols([trade.trading_symbol])
                self.registered_symbols.append(trade.trading_symbol)
        logging.info("TradeManager: Successfully loaded %d trades from json file %s", len(self.trades), trades_filepath)

    def load_strategies_from_file(self):
        strategies_filePath = self.get_strategies_filepath()
        if os.path.exists(strategies_filePath) == False:
            logging.warn("TradeManager: load_strategies_from_file() Strategies Filepath %s does not exist", strategies_filePath)
            return
        sFile = open(strategies_filePath, "r")
        self.strategies_data = json.loads(sFile.read())
        logging.info("TradeManager: Successfully loaded %d strategies from json file %s", len(self.strategies_data), strategies_filePath)

    def get_trades_filepath(self):
        tradesFilepath = os.path.join(
            self.intradayTradesDir, get_user_details(self.short_code).broker_name + "_" + get_user_details(self.short_code).client_id + ".json"
        )
        return tradesFilepath

    def get_strategies_filepath(self):
        tradesFilepath = os.path.join(
            self.intradayTradesDir, get_user_details(self.short_code).broker_name + "_" + get_user_details(self.short_code).client_id + "_strategies.json"
        )
        return tradesFilepath

    def save_trades_to_file(self):
        tradesFilepath = self.get_trades_filepath()
        with open(tradesFilepath, "w") as tFile:
            json.dump(self.trades, tFile, indent=2, cls=TradeEncoder)
        logging.debug("TradeManager: Saved %d trades to file %s", len(self.trades), tradesFilepath)

    def save_strategies_to_file(self):
        strategiesFilePath = self.get_strategies_filepath()
        with open(strategiesFilePath, "w") as tFile:
            json.dump(self.strategy_to_instance, tFile, indent=2, cls=TradeEncoder)
        logging.debug("TradeManager: Saved %d strategies to file %s", len(self.strategy_to_instance.values()), strategiesFilePath)


class TradeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        if isinstance(o, BaseStrategy):
            return o.asDict()
        if isinstance(o, Enum):
            return o.name
        return o.__dict__


def convert_json_to_order(jsonData):
    if jsonData == None:
        return None
    order = Order(None)
    order.trading_symbol = jsonData["trading_symbol"]
    order.exchange = jsonData["exchange"]
    order.product_type = ProductType[jsonData["product_type"]]
    order.order_type = OrderType[jsonData["order_type"]]
    order.price = jsonData["price"]
    order.trigger_price = jsonData["trigger_price"]
    order.qty = jsonData["qty"]
    order.order_id = jsonData["order_id"]
    order.order_status = jsonData["order_status"]
    order.average_price = jsonData["average_price"]
    order.filled_qty = jsonData["filled_qty"]
    order.pending_qty = jsonData["pending_qty"]
    order.place_timestamp = jsonData["place_timestamp"]
    order.update_timestamp = jsonData["update_timestamp"]
    order.message = jsonData["message"]
    order.parent_order_id = jsonData.get("parent_order_id", "")
    return order


def convert_json_to_trade(jsonData):
    trade = Trade(jsonData["trading_symbol"])
    trade.trade_id = jsonData["trade_id"]
    trade.strategy = jsonData["strategy"]
    trade.direction = Direction[jsonData["direction"]]
    trade.product_type = ProductType[jsonData["product_type"]]
    trade.is_futures = jsonData["is_futures"]
    trade.is_options = jsonData["is_options"]
    trade.option_type = jsonData["option_type"]
    trade.underLying = jsonData.get("underLying", "")
    trade.place_market_order = jsonData["place_market_order"]
    trade.intraday_squareoff_timestamp = jsonData["intraday_squareoff_timestamp"]
    trade.requested_entry = jsonData["requested_entry"]
    trade.entry = jsonData["entry"]
    trade.qty = jsonData["qty"]
    trade.filled_qty = jsonData["filled_qty"]
    trade.initial_stoploss = jsonData["initial_stoploss"]
    trade.stopLoss = jsonData["_stopLoss"]
    trade.stoploss_percentage = jsonData.get("stoploss_percentage", 0.0)
    trade.stoploss_underlying_percentage = jsonData.get("stoploss_underlying_percentage", 0.0)
    trade.target = jsonData["target"]
    trade.cmp = jsonData["cmp"]
    trade.state = TradeState[jsonData["state"]]
    trade.timestamp = jsonData["timestamp"]
    trade.create_timestamp = jsonData["create_timestamp"]
    trade.start_timestamp = jsonData["start_timestamp"]
    trade.end_timestamp = jsonData["end_timestamp"]
    trade.pnl = jsonData["pnl"]
    trade.pnl_percentage = jsonData["pnl_percentage"]
    trade.exit = jsonData["exit"]
    trade.exit_reason = jsonData["exit_reason"]
    trade.exchange = jsonData["exchange"]
    trade.sl_orders
    for entry_order in jsonData["entry_orders"]:
        trade.entry_orders.append(convert_json_to_order(entry_order))
    for sl_order in jsonData["sl_orders"]:
        trade.sl_orders.append(convert_json_to_order(sl_order))
    for target_order in jsonData["target_orders"]:
        trade.target_orders.append(convert_json_to_order(target_order))
    return trade
