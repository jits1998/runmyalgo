import asyncio
import datetime
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Type

import instruments
from broker import BaseHandler
from core.strategy import BaseStrategy, StartTimedBaseStrategy
from core.tradeManager import TradeManager
from exceptions import DeRegisterStrategyException
from models import UserDetails


class BaseAlgo(threading.Thread, ABC):
    access_token: str
    short_code: str
    user_details: UserDetails
    trade_manager: TradeManager
    broker_handler: BaseHandler

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None):
        super(BaseAlgo, self).__init__(group=group, target=target, name=name)
        (
            self.access_token,
            self.short_code,
            self.multiple,
        ) = args
        self.trade_manager = None
        self.broker_handler = None
        self.tasks = []

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.run_forever()

    def start_algo(self):

        if self.trade_manager is not None:
            logging.info("Algo has already started..")
            return

        logging.info("Starting Algo...")

        all_instruments = instruments.fetch_instruments(self.short_code, self.broker_handler)

        if len(all_instruments) == 0:
            # something is wrong. We need to inform the user
            logging.warn("Algo not started.")
            return

        asyncio.set_event_loop(self.loop)

        tm = TradeManager(self.short_code, self.access_token, self.broker_handler)
        self.trade_manager = tm

        tm_task = asyncio.run_coroutine_threadsafe(tm.run(), self.loop)
        self.tasks.append(tm_task)

        tm__order_task = asyncio.run_coroutine_threadsafe(tm.place_orders(), self.loop)
        self.tasks.append(tm__order_task)

        # breaking here to move to async mode

        # sleep for 2 seconds for TradeManager to get initialized
        while not self.trade_manager.is_ready:
            if not self.trade_manager.is_alive():
                logging.info("Ending Algo...")
                return
            time.sleep(2)

        start_strategies_fut = asyncio.run_coroutine_threadsafe(self.start_strategies(self.short_code, self.multiple), self.loop)
        self.tasks.append(start_strategies_fut)

        logging.info("Algo started.")

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
        strategy_instance.trades = self.trade_manager.get_trades_by_strategy(strategy_instance.getName())
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
