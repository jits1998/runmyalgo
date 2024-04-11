import asyncio
import datetime
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

import psycopg2

import instruments
from broker import BaseHandler, brokers
from broker.base import BaseTicker
from config import get_server_config
from core.strategy import BaseStrategy, StartTimedBaseStrategy
from exceptions import DeRegisterStrategyException
from instruments import symbol_to_CMP as cmp
from models import AlgoStatus, TradeState, UserDetails
from models.order import Order
from models.trade import Trade
from utils import (
    get_epoch,
    get_today_date_str,
    get_user_details,
    is_market_closed_for_the_day,
    is_today_holiday,
)


class BaseAlgo(threading.Thread, ABC):
    access_token: str
    short_code: str
    user_details: UserDetails
    broker_handler: BaseHandler
    loop: asyncio.AbstractEventLoop

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None) -> None:
        super(BaseAlgo, self).__init__(group=group, target=target, name=name)
        (
            self.access_token,
            self.short_code,
            self.multiple,
        ) = args
        self.tasks: List[asyncio.Task] = []
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.order_queue: asyncio.Queue[Trade] = asyncio.Queue()
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

        all_instruments = instruments.fetch_instruments(self.short_code, self.broker_handler)

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

        self.order_manager = brokers[get_user_details(self.short_code).broker]["order_manager"](self.short_code, self.broker_handler)

        self.ticker = brokers[get_user_details(self.short_code).broker]["ticker"](self.short_code, self.broker_handler)
        assert isinstance(self.ticker, BaseTicker)

        self.ticker.start_ticker(get_user_details(self.short_code).key, self.access_token)
        self.ticker.register_listener(self.ticker_listener)

        self.ticker.register_symbols(["NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY FIN SERVICE"])

        # Load all trades from json files to app memory
        self.load_trades_from_file()
        self.load_strategies_from_file()

        while len(self.symbol_to_cmp) < 4:
            time.sleep(2)

        self.status = AlgoStatus.STARTED

        # tm = TradeManager(self.short_code, self.access_token, self.broker_handler)
        # self.trade_manager = tm

        play_task = asyncio.run_coroutine_threadsafe(self.play(), self.loop)
        self.tasks.append(play_task)

        order_task = asyncio.run_coroutine_threadsafe(self.place_orders(), self.loop)
        self.tasks.append(order_task)

        start_strategies_fut = asyncio.run_coroutine_threadsafe(self.start_strategies(self.short_code, self.multiple), self.loop)
        self.tasks.append(start_strategies_fut)

        logging.info("Algo started.")

    async def play(self):  # track and update trades in a loop
        while True:

            if self.questDBCursor is None or self.questDBCursor.closed:
                self.questDBCursor = self.get_questdb_connection()

            if not is_today_holiday() and not is_market_closed_for_the_day() and not len(self.strategy_to_instance) == 0:
                # try:
                #     # Fetch all order details from broker and update orders in each trade
                #     self.fetchAndUpdateAllTradeOrders()
                #     # track each trade and take necessary action
                #     self.trackAndUpdateAllTrades()

                #     self.checkStrategyHealth()
                #     # print ( "%s =>%f :: %f" %(datetime.now().strftime("%H:%M:%S"), pe_vega, ce_vega))
                # except Exception as e:
                #     traceback.print_exc()
                #     logging.exception("Exception in TradeManager Main thread")

                # save updated data to json file
                self.save_trades_to_file()
                self.save_strategies_to_file()

            now = datetime.datetime.now()
            waitSeconds = 5 - (now.second % 5)
            await asyncio.sleep(waitSeconds)

    async def place_orders(self):
        while True:
            trade: Trade = await self.order_queue.get()  # type: ignore
            try:
                strategyInstance = self.strategy_to_instance[trade.strategy]
                if strategyInstance.shouldPlaceTrade(trade):
                    # place the longTrade
                    isSuccess = self.execute_trade(trade)
                    if isSuccess == True:
                        # set longTrade state to ACTIVE
                        trade.tradeState = TradeState.ACTIVE
                        trade.startTimestamp = get_epoch()
                        continue
            except Exception as e:
                logging.warn(str(e))

            trade.tradeState = TradeState.DISABLED

    @abstractmethod
    async def start_strategies(self, short_code, multiple=0): ...

    async def start_strategy(self, strategy: Type[BaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        strategy_instance = strategy(short_code, self.broker_handler, multiple)  # type: ignore
        self._start_strategy(strategy_instance, run)

    async def start_timed_strategy(
        self, strategy: Type[StartTimedBaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None
    ):
        strategy_instance = strategy(short_code, startTimestamp, self.broker_handler, multiple)
        self._start_strategy(strategy_instance, run)

    def _start_strategy(self, strategy_instance, run):
        strategy_instance.trades = self.get_trades_by_strategy(strategy_instance.getName())
        strategy_instance.runConfig = run

        strategy_task = asyncio.create_task(strategy_instance.run())
        strategy_task.set_name(strategy_instance.getName())
        strategy_task.add_done_callback(self.handle_exception)

        self.tasks.append(strategy_task)
        self.trade_manager.register_strategy(strategy_instance)

    def handle_exception(self, task):
        if task.exception() is not None:
            logging.info("Exception in %s", task.get_name())
            logging.info(task.exception())
            if isinstance(task.exception(), DeRegisterStrategyException):
                self.trade_manager.dergister_strategy(task.get_name())
                pass

    def ticker_listener(self, tick):
        logging.debug("tickerLister: new tick received for %s = %f", tick.trading_symbol, tick.lastTradedPrice)
        # Store the latest tick in map
        self.symbol_to_cmp[tick.trading_symbol] = tick.lastTradedPrice
        if tick.exchange_timestamp:
            self.symbol_to_cmp["exchange_timestamp"] = tick.exchange_timestamp

    def get_trades_by_strategy(self, strategy: str):
        tradesByStrategy = []
        for trade in self.trades:
            if trade.strategy == strategy:
                tradesByStrategy.append(trade)
        return tradesByStrategy

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
            trade = self.convert_json_to_trade(tr)
            logging.info("load_trades_from_file trade => %s", trade)
            self.trades.append(trade)
            if trade.trading_symbol not in self.registeredSymbols:
                # Algo register symbols with ticker
                self.ticker.register_symbols([trade.trading_symbol])
                self.registeredSymbols.append(trade.trading_symbol)
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
            self.intradayTradesDir, get_user_details(self.short_code).broker + "_" + get_user_details(self.short_code).clientID + ".json"
        )
        return tradesFilepath

    def get_strategies_filepath(self):
        tradesFilepath = os.path.join(
            self.intradayTradesDir, get_user_details(self.short_code).broker + "_" + get_user_details(self.short_code).clientID + "_strategies.json"
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
        return o.__dict__