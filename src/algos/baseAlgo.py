import asyncio
import datetime
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Type

import instruments
from broker import BaseHandler, brokers, load_broker_module
from core.strategy import BaseStrategy, StartTimedBaseStrategy
from core.tradeManager import TradeManager
from exceptions import DeRegisterStrategyException
from models import UserDetails
from utils import findNumberOfDaysBeforeWeeklyExpiryDay, isTodayWeeklyExpiryDay


class BaseAlgo(threading.Thread, ABC):
    accessToken: str
    short_code: str
    userDetails: UserDetails
    tradeManager: TradeManager
    brokerHandler: BaseHandler

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None):
        super(BaseAlgo, self).__init__(group=group, target=target, name=name)
        (
            self.accessToken,
            self.short_code,
            self.multiple,
        ) = args
        self.tradeManager = None
        self.brokerHandler = None
        self.tasks = []

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.run_forever()

    def startAlgo(self):

        if self.tradeManager is not None:
            logging.info("Algo has already started..")
            return

        logging.info("Starting Algo...")

        instrumentsList = instruments.fetchInstruments(self.short_code, self.brokerHandler)

        if len(instrumentsList) == 0:
            # something is wrong. We need to inform the user
            logging.warn("Algo not started.")
            return

        asyncio.set_event_loop(self.loop)

        tm = TradeManager(self.short_code, self.accessToken, self.brokerHandler)
        self.tradeManager = tm

        tm_task = asyncio.run_coroutine_threadsafe(tm.run(), self.loop)
        self.tasks.append(tm_task)

        tm__order_task = asyncio.run_coroutine_threadsafe(tm.placeOrders(), self.loop)
        self.tasks.append(tm__order_task)

        # breaking here to move to async mode

        # sleep for 2 seconds for TradeManager to get initialized
        while not self.tradeManager.isReady:
            if not self.tradeManager.is_alive():
                logging.info("Ending Algo...")
                return
            time.sleep(2)

        start_strategies_fut = asyncio.run_coroutine_threadsafe(self.startStrategies(self.short_code, self.multiple), self.loop)
        self.tasks.append(start_strategies_fut)

        logging.info("Algo started.")

    @abstractmethod
    async def startStrategies(self, short_code, multiple=0): ...

    async def startStrategy(self, strategy: Type[BaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        strategyInstance = strategy(short_code, self.brokerHandler, multiple)  # type: ignore
        self._startStrategy(strategyInstance, run)

    async def startTimedStrategy(self, strategy: Type[StartTimedBaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None):
        strategyInstance = strategy(short_code, startTimestamp, self.brokerHandler, multiple)
        self._startStrategy(strategyInstance, run)

    def _startStrategy(self, strategyInstance, run):
        strategyInstance.trades = self.tradeManager.getAllTradesByStrategy(strategyInstance.getName())
        strategyInstance.runConfig = run

        strategy_task = asyncio.create_task(strategyInstance.run())
        strategy_task.set_name(strategyInstance.getName())
        strategy_task.add_done_callback(self.handleException)

        self.tasks.append(strategy_task)
        self.tradeManager.registerStrategy(strategyInstance)

    def handleException(self, task):
        if task.exception() is not None:
            logging.info("Exception in %s", task.get_name())
            logging.info(task.exception())
            if isinstance(task.exception(), DeRegisterStrategyException):
                self.tradeManager.deRgisterStrategy(task.get_name())
                pass
