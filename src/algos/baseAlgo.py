import datetime
import logging
import threading
import time

import instruments
from broker import brokers, load_broker_module
from utils import getBrokerLogin, getTradeManager, getUserDetails

# from Test import Test


class BaseAlgo:

    def __init__(self):
        self.strategyConfig = {}

    def startAlgo(self, accessToken, short_code, multiple=0):
        if getTradeManager(short_code) is not None:
            logging.info("Algo has already started..")
            return

        logging.info("Starting Algo...")

        if getBrokerLogin(short_code) is None:
            userDetails = getUserDetails(short_code)
            userDetails.start()
            load_broker_module(userDetails.broker)
            loginHandler: BaseLogin = brokers[userDetails.broker]["LoginHandler"](userDetails.__dict__)
            loginHandler.login({})
            userDetails.loginHandler = loginHandler
            brokerLogin = getBrokerLogin(short_code)
            brokerLogin.setAccessToken(accessToken)
            brokerLogin.getBrokerHandle().set_access_token(accessToken)

        instrumentsList = instruments.fetchInstruments(short_code)

        if len(instrumentsList) == 0:
            # something is wrong. We need to inform the user
            logging.warn("Algo not started.")
            return

        # start trade manager in a separate thread
        tm = TradeManager(
            name=short_code,
            args=(
                accessToken,
                self,
            ),
        )
        tm.start()

        # sleep for 2 seconds for TradeManager to get initialized
        while not Utils.getTradeManager(short_code).isReady:
            if not tm.is_alive():
                logging.info("Ending Algo...")
                return
            time.sleep(2)

        self.startStrategies(short_code, multiple)

        logging.info("Algo started.")

    def startStrategies(self, short_code, multiple=0):
        pass

    def startStrategy(self, strategy, short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        # threading.Thread(target=FN_SBT_Expiry(short_code).run, name=short_code + "_" + FN_SBT_Expiry.getInstance(short_code).getName()).start()

        threading.Thread(target=strategy(short_code, multiple).run, name=short_code + "_" + strategy.getInstance(short_code).getName()).start()

        self.strategyConfig[strategy.getInstance(short_code).getName()] = run

    def startTimedStrategy(self, strategy, short_code, multiple, run=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], startTimestamp=None):

        strategyInstance = strategy(short_code, multiple, startTimestamp=startTimestamp)

        threading.Thread(target=strategyInstance.run, name=short_code + "_" + strategyInstance.getName()).start()

        self.strategyConfig[strategyInstance.getName()] = run

    def getLots(self, strategyName, symbol, expiryDay):

        strategyLots = self.strategyConfig.get(strategyName, [0, -1, -1, -1, -1, -1, 0, 0, 0, 0])

        if Utils.isTodayWeeklyExpiryDay(symbol, expiryDay):
            return strategyLots[0]

        noOfDaysBeforeExpiry = Utils.findNumberOfDaysBeforeWeeklyExpiryDay(symbol, expiryDay)
        if strategyLots[-noOfDaysBeforeExpiry] > 0:
            return strategyLots[-noOfDaysBeforeExpiry]

        dayOfWeek = datetime.datetime.now().weekday() + 1  # adding + 1 to set monday index as 1
        # this will handle the run condition during thread start by defaulting to -1, and thus wait in get Lots
        if dayOfWeek >= 1 and dayOfWeek <= 5:
            return strategyLots[dayOfWeek]

        logging.info(strategyName + "::" + str(strategyLots))
        return 0
