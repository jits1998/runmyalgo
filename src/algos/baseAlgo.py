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

    def run(self):
        while True:
            time.sleep(10)

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

        # start trade manager in a separate thread
        tm = TradeManager(self.short_code, self.accessToken, self.brokerHandler)
        self.tradeManager = tm
        tm.run  # breaking here to move to async mode

        # sleep for 2 seconds for TradeManager to get initialized
        while not tm.isReady:
            if not tm.is_alive():
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
        threading.Thread(target=strategyInstance.run, name=short_code + "_" + strategyInstance.getName()).start()
        self.strategyConfig[strategyInstance.getName()] = run

    def startTimedStrategy(self, strategy: Type[StartTimedBaseStrategy], short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None):
        strategyInstance = strategy(short_code, multiple, self.brokerHandler, startTimestamp)
        self.tradeManager.registerStrategy(strategyInstance)
        strategyInstance.trades = self.tradeManager.getAllTradesByStrategy(strategyInstance.getName())
        threading.Thread(target=strategyInstance.run, name=short_code + "_" + strategyInstance.getName()).start()
        self.strategyConfig[strategyInstance.getName()] = run

    def getLots(self, strategyName, symbol, expiryDay):
        strategyLots = self.strategyConfig.get(strategyName, [0, -1, -1, -1, -1, -1, 0, 0, 0, 0])
        if isTodayWeeklyExpiryDay(symbol, expiryDay):
            return strategyLots[0]
        noOfDaysBeforeExpiry = findNumberOfDaysBeforeWeeklyExpiryDay(symbol, expiryDay)
        if strategyLots[-noOfDaysBeforeExpiry] > 0:
            return strategyLots[-noOfDaysBeforeExpiry]
        dayOfWeek = datetime.datetime.now().weekday() + 1  # adding + 1 to set monday index as 1
        # this will handle the run condition during thread start by defaulting to -1, and thus wait in get Lots
        if dayOfWeek >= 1 and dayOfWeek <= 5:
            return strategyLots[dayOfWeek]
        logging.info(strategyName + "::" + str(strategyLots))
        return 0
