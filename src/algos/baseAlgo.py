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

# from utils import getBrokerLogin, getTradeManager, getUserDetails

# from Test import Test


class BaseAlgo(threading.Thread, ABC):
    accessToken: str
    short_code: str
    userDetails: UserDetails
    trademanager: TradeManager
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
        self.strategyConfig = {}
        self.tasks = []

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
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

        tm_task = asyncio.run(tm.run())
        self.tasks.append(tm_task)

        # breaking here to move to async mode

        # sleep for 2 seconds for TradeManager to get initialized
        while not self.tradeManager.isReady:
            if not self.tradeManager.is_alive():
                logging.info("Ending Algo...")
                return
            time.sleep(2)

        self.startStrategies(self.short_code, self.multiple)

        logging.info("Algo started.")

    @abstractmethod
    def startStrategies(self, short_code, multiple=0): ...

    def startStrategy(self, strategy: Type[BaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        strategyInstance = strategy(short_code, multiple, self.brokerHandler)
        self.tradeManager.registerStrategy(strategyInstance)
        strategyInstance.trades = self.tradeManager.getAllTradesByStrategy(strategyInstance.getName())
        strategy_task: asyncio.Task = asyncio.run(strategyInstance.run())
        strategy_task.set_name(short_code + "_" + strategyInstance.getName())
        strategy_task.add_done_callback(self.handleException)
        self.tasks.append(strategy_task)
        # threading.Thread(target=strategyInstance.run, name=short_code + "_" + strategyInstance.getName()).start()
        self.strategyConfig[strategyInstance.getName()] = run

    def startTimedStrategy(self, strategy: Type[StartTimedBaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None):
        strategyInstance = strategy(short_code, multiple, self.brokerHandler, startTimestamp)
        self.tradeManager.registerStrategy(strategyInstance)
        strategyInstance.trades = self.tradeManager.getAllTradesByStrategy(strategyInstance.getName())
        strategy_task = asyncio.run(strategyInstance.run())
        strategy_task.set_name(short_code + "_" + strategyInstance.getName())
        strategy_task.add_done_callback(self.handleException)
        self.tasks.append(strategy_task)

    def handleException(self, task):
        if task.exception() is not None:
            logging.info("Exception in %s", task.get_name())
            logging.info(task.exception())
            if isinstance(task.exception(), DeRegisterStrategyException):
                # disable strategy
                pass
