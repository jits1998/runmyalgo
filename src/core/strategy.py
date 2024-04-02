import asyncio
import logging
import math
import time
from datetime import datetime
from math import ceil
from typing import List

from broker.base import BaseHandler
from core import Quote
from exceptions import DeRegisterStrategyException, DisableTradeException
from instruments import getCMP, getInstrumentDataBySymbol, symbolToCMPMap
from models import ProductType, TradeExitReason
from models.trade import Trade
from utils import (
    findNumberOfDaysBeforeWeeklyExpiryDay,
    getEpoch,
    getMarketStartTime,
    getNearestStrikePrice,
    isMarketClosedForTheDay,
    isTodayWeeklyExpiryDay,
    prepareMonthlyExpiryFuturesSymbol,
    prepareWeeklyOptionsSymbol,
    waitTillMarketOpens,
)


class BaseStrategy:

    def __init__(self, name: str, short_code: str, handler: BaseHandler, multiple: int = 0):
        # NOTE: All the below properties should be set by the Derived Class (Specific to each strategy)
        self.name = name  # strategy name
        self.short_code = short_code
        self.orderQueue: asyncio.Queue
        self.handler = handler
        self.enabled = True  # Strategy will be run only when it is enabled
        self.productType = ProductType.MIS  # MIS/NRML/CNC etc
        self.symbols: List[str] = []  # List of stocks to be traded under this strategy
        self.slPercentage = 0
        self.targetPercentage = 0
        self.startTimestamp = getMarketStartTime()  # When to start the strategy. Default is Market start time
        self.stopTimestamp = None  # This is not square off timestamp. This is the timestamp after which no new trades will be placed under this strategy but existing trades continue to be active.
        self.squareOffTimestamp = None  # Square off time
        self.maxTradesPerDay = 1  # Max number of trades per day under this strategy
        self.isFnO = True  # Does this strategy trade in FnO or not
        self.strategySL = 0
        self.strategyTarget = 0
        # Load all trades of this strategy into self.trades on restart of app
        self.trades: List[Trade] = []
        self.expiryDay = 2
        self.symbol = "BANKNIFTY"
        self.multiple = multiple
        self.exchange = "NFO"
        self.equityExchange = "NSE"

    def getName(self):
        return self.name

    def isEnabled(self):
        return self.enabled

    def setDisabled(self):
        self.enabled = False

    def getMultiple(self):
        return float(self.multiple)

    def getLots(self):
        lots = self._getLots(self.getName(), self.symbol, self.expiryDay) * self.getMultiple()

        if isTodayWeeklyExpiryDay("NIFTY", expiryDay=3) and isTodayWeeklyExpiryDay("BANKNIFTY", expiryDay=2):
            lots = lots * 0.5

        if isTodayWeeklyExpiryDay("FINNIFTY", expiryDay=1) and isTodayWeeklyExpiryDay("BANKNIFTY", expiryDay=2):
            lots = lots * 0.5

        if (
            isTodayWeeklyExpiryDay("NIFTY", expiryDay=3)
            and isTodayWeeklyExpiryDay("FINNIFTY", expiryDay=1)
            and isTodayWeeklyExpiryDay("BANKNIFTY", expiryDay=2)
        ):
            lots = lots * 0.33

        return ceil(lots)

    async def process(self):
        # Implementation is specific to each strategy - To defined in derived class
        logging.info("BaseStrategy process is called.")
        pass

    def isTargetORSLHit(self):
        if self.strategySL == 0 and self.strategyTarget == 0:
            return None

        totalPnl = sum([trade.pnl for trade in self.trades])
        exitTrade = False
        reason = None

        if totalPnl < (self.strategySL * self.getLots()):
            if self.strategySL < 0:
                exitTrade = True
                reason = TradeExitReason.STRATEGY_SL_HIT
            if self.strategySL > 0:
                exitTrade = True
                reason = TradeExitReason.STRATEGY_TRAIL_SL_HIT
        elif self.strategyTarget > 0 and totalPnl > (self.strategyTarget * self.getLots()):
            self.strategySL = 0.9 * totalPnl / self.getLots()
            logging.warn(
                "Strategy Target %d hit for %s @ PNL per lot = %d, Updated SL to %d ",
                self.strategyTarget,
                self.getName(),
                totalPnl / self.getLots(),
                self.strategySL,
            )
            self.strategyTarget = 0  # no more targets, will trail SL
        elif self.strategySL > 0 and self.strategySL * 1.2 < totalPnl / self.getLots():
            self.strategySL = 0.9 * totalPnl / self.getLots()
            logging.warn("Updated Strategy SL for %s to %d @ PNL per lot = %d", self.getName(), self.strategySL, totalPnl / self.getLots())

        if exitTrade:
            logging.warn("Strategy SL Hit for %s at %d with PNL per lot = %d", self.getName(), self.strategySL, totalPnl / self.getLots())
            return reason
        else:
            return None

    def canTradeToday(self):
        # if the run is not set, it will default to -1, thus wait
        while self.getLots() == -1:
            time.sleep(2)

        # strategy will run only if the number of lots is > 0
        return self.getLots() > 0

    def getVIXThreshold(self):
        return 0

    async def run(self):

        self.fromDict(self.strategyData)

        if self.strategyData is None:  # Enabled status, SLs and target may have been adjusted

            # NOTE: This should not be overriden in Derived class
            if self.enabled == False:
                raise DeRegisterStrategyException("Strategy is disabled. Can't run it.")

            if self.strategySL > 0:
                raise DeRegisterStrategyException("strategySL < 0. Can't run it.")

            self.strategySL = self.strategySL * self.getVIXAdjustment(self.short_code)
            self.strategyTarget = self.strategyTarget * self.getVIXAdjustment(self.short_code)

            if isMarketClosedForTheDay():
                raise DeRegisterStrategyException("Market is closed, Can't run it")

        for trade in self.trades:
            if trade.exitReason not in [None, TradeExitReason.SL_HIT, TradeExitReason.TARGET_HIT, TradeExitReason.TRAIL_SL_HIT, TradeExitReason.MANUAL_EXIT]:
                logging.warn("Exiting %s as a trade found with %s", self.getName(), trade.exitReason)
                return  # likely something at strategy level or broker level, won't continue

        if self.canTradeToday() == False:
            raise DeRegisterStrategyException("Can't be traded today.")

        now = datetime.now()
        if now < getMarketStartTime():
            waitTillMarketOpens(self.getName())

        now = datetime.now()
        if now < self.startTimestamp:
            waitSeconds = getEpoch(self.startTimestamp) - getEpoch(now)
            logging.info("%s: Waiting for %d seconds till startegy start timestamp reaches...", self.getName(), waitSeconds)
            if waitSeconds > 0:
                time.sleep(waitSeconds)

        if self.getVIXThreshold() > getCMP(self.short_code, "INDIA VIX"):
            raise DeRegisterStrategyException("VIX threshold is not met. Can't run it!")

        # Run in an loop and keep processing
        while True:

            if isMarketClosedForTheDay() or not self.isEnabled():
                logging.warn("%s: Exiting the strategy as market closed or strategy was disabled.", self.getName())
                break

            now = datetime.now()
            if now > self.squareOffTimestamp:
                self.setDisabled()
                logging.warn("%s: Disabled the strategy as Squareoff time is passed.", self.getName())

                return

            # Derived class specific implementation will be called when process() is called
            await self.process()

            # Sleep and wake up 5s after every 15th second, ie after trade manager has updated trades

            waitSeconds = 5 - (now.second % 5) + 3
            await asyncio.sleep(waitSeconds)

    def shouldPlaceTrade(self, trade, tick):
        # Each strategy should call this function from its own shouldPlaceTrade() method before working on its own logic
        if trade == None:
            return False
        if trade.qty == 0:
            raise DisableTradeException("Invalid Quantity")

        now = datetime.now()
        if now > self.stopTimestamp:
            raise DisableTradeException("NoNewTradesCutOffTimeReached")

        numOfTradesPlaced = len(self.trades)
        if numOfTradesPlaced >= self.maxTradesPerDay:
            raise DisableTradeException("MaxTradesPerDayReached")

        return True

    def addTradeToList(self, trade):
        if trade != None:
            self.trades.append(trade)

    def getQuote(self, tradingSymbol):
        try:
            return self.handler.getQuote(tradingSymbol, self.short_code, self.isFnO, self.exchange)
        except KeyError as e:
            logging.info("%s::%s: Could not get Quote for %s => %s", self.short_code, self.getName(), tradingSymbol, str(e))
        except Exception as exp:
            logging.info("%s::%s: Could not get Quote for %s => %s", self.short_code, self.getName(), tradingSymbol, str(exp))

        return Quote(tradingSymbol)

    def getTrailingSL(self, trade):
        return 0

    def generateTrade(self, optionSymbol, direction, numLots, lastTradedPrice, slPercentage=0, slPrice=0, targetPrice=0, placeMarketOrder=True):
        trade = Trade(optionSymbol, self.getName())
        trade.isOptions = True
        trade.exchange = self.exchange
        trade.direction = direction
        trade.productType = self.productType
        trade.placeMarketOrder = placeMarketOrder
        trade.requestedEntry = lastTradedPrice
        trade.timestamp = getEpoch(self.startTimestamp)  # setting this to strategy timestamp

        trade.stopLossPercentage = slPercentage
        trade.stopLoss = slPrice  # if set to 0, then set stop loss will be set after entry via trailingSL method
        trade.target = targetPrice

        isd = getInstrumentDataBySymbol(self.short_code, optionSymbol)  # Get instrument data to know qty per lot
        trade.qty = isd["lot_size"] * numLots

        trade.intradaySquareOffTimestamp = getEpoch(self.squareOffTimestamp)
        # Hand over the trade to TradeManager
        self.orderQueue.put(trade)

    def generateTradeWithSLPrice(self, optionSymbol, direction, numLots, lastTradedPrice, underLying, underLyingStopLossPercentage, placeMarketOrder=True):
        trade = Trade(optionSymbol, self.getName())
        trade.isOptions = True
        trade.exchange = self.exchange
        trade.direction = direction
        trade.productType = self.productType
        trade.placeMarketOrder = placeMarketOrder
        trade.requestedEntry = lastTradedPrice
        trade.timestamp = getEpoch(self.startTimestamp)  # setting this to strategy timestamp

        trade.underLying = underLying
        trade.stopLossUnderlyingPercentage = underLyingStopLossPercentage

        isd = getInstrumentDataBySymbol(self.short_code, optionSymbol)  # Get instrument data to know qty per lot
        trade.qty = isd["lot_size"] * numLots

        trade.stopLoss = 0
        trade.target = 0  # setting to 0 as no target is applicable for this trade

        trade.intradaySquareOffTimestamp = getEpoch(self.squareOffTimestamp)
        # Hand over the trade to TradeManager
        self.orderQueue.put(trade)

    def getStrikeWithNearestPremium(self, optionType, nearestPremium, roundToNearestStrike=100):
        # Get the nearest premium strike price
        futureSymbol = prepareMonthlyExpiryFuturesSymbol(self.symbol, self.expiryDay)
        quote = self.getQuote(futureSymbol)
        if quote == None or quote.lastTradedPrice == 0:
            logging.error("%s: Could not get quote for %s", self.getName(), futureSymbol)
            return

        strikePrice = getNearestStrikePrice(quote.lastTradedPrice, roundToNearestStrike)
        premium = -1

        lastPremium = premium
        lastStrike = strikePrice

        while premium < nearestPremium:  # check if we need to go ITM
            premium = self.getQuote(prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)).lastTradedPrice
            if optionType == "CE":
                strikePrice = strikePrice - roundToNearestStrike
            else:
                strikePrice = strikePrice + roundToNearestStrike

        while True:
            try:
                symbol = prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)
                try:
                    getInstrumentDataBySymbol(self.short_code, symbol)
                except KeyError:
                    logging.info("%s: Could not get instrument for %s", self.getName(), symbol)
                    return lastStrike, lastPremium

                quote = self.getQuote(symbol)

                if quote.totalSellQuantity == 0 and quote.totalBuyQuantity == 0:
                    time.sleep(1)
                    quote = self.getQuote(symbol)  # lets try one more time.

                premium = quote.lastTradedPrice

                if premium > nearestPremium:
                    lastPremium = premium
                else:
                    # quote.lastTradedPrice < quote.upperCircuitLimit and quote.lastTradedPrice > quote.lowerCiruitLimit and \
                    if (
                        (lastPremium - nearestPremium) > (nearestPremium - premium)
                        and quote.volume > 0
                        and quote.totalSellQuantity > 0
                        and quote.totalBuyQuantity > 0
                    ):
                        return strikePrice, premium
                    else:
                        logging.info(
                            "%s: Returning previous strike for %s as vol = %s sell = %s buy = %s",
                            self.getName(),
                            symbol,
                            quote.volume,
                            quote.totalSellQuantity,
                            quote.totalBuyQuantity,
                        )
                        return lastStrike, lastPremium

                lastStrike = strikePrice
                lastPremium = premium

                if optionType == "CE":
                    strikePrice = strikePrice + roundToNearestStrike
                else:
                    strikePrice = strikePrice - roundToNearestStrike
                time.sleep(1)
            except KeyError:
                return lastStrike, lastPremium

    def getStrikeWithMinimumPremium(self, optionType, minimumPremium, roundToNearestStrike=100):
        # Get the nearest premium strike price
        futureSymbol = prepareMonthlyExpiryFuturesSymbol(self.symbol, self.expiryDay)
        quote = self.getQuote(futureSymbol)
        if quote == None or quote.lastTradedPrice == 0:
            logging.error("%s: Could not get quote for %s", self.getName(), futureSymbol)
            return

        strikePrice = getNearestStrikePrice(quote.lastTradedPrice, roundToNearestStrike)
        premium = -1

        lastPremium = premium
        lastStrike = strikePrice

        while premium < minimumPremium:  # check if we need to go ITM
            premium = self.getQuote(prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)).lastTradedPrice
            if optionType == "CE":
                strikePrice = strikePrice - roundToNearestStrike
            else:
                strikePrice = strikePrice + roundToNearestStrike

        while True:
            try:
                symbol = prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)
                getInstrumentDataBySymbol(self.short_code, symbol)
                quote = self.getQuote(symbol)

                if quote.totalSellQuantity == 0 and quote.totalBuyQuantity == 0:
                    time.sleep(1)
                    quote = self.getQuote(symbol)  # lets try one more time.

                premium = quote.lastTradedPrice

                if premium < minimumPremium:
                    return lastStrike, lastPremium

                lastStrike = strikePrice
                lastPremium = premium

                if optionType == "CE":
                    strikePrice = strikePrice + roundToNearestStrike
                else:
                    strikePrice = strikePrice - roundToNearestStrike
                time.sleep(1)
            except KeyError:
                return lastStrike, lastPremium

    def getStrikeWithMaximumPremium(self, optionType, maximumPremium, roundToNearestStrike=100):
        # Get the nearest premium strike price
        futureSymbol = prepareMonthlyExpiryFuturesSymbol(self.symbol, self.expiryDay)
        quote = self.getQuote(futureSymbol)
        if quote == None or quote.lastTradedPrice == 0:
            logging.error("%s: Could not get quote for %s", self.getName(), futureSymbol)
            return

        strikePrice = getNearestStrikePrice(quote.lastTradedPrice, roundToNearestStrike)
        premium = -1

        lastPremium = premium
        lastStrike = strikePrice

        while premium < maximumPremium:  # check if we need to go ITM
            premium = self.getQuote(prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)).lastTradedPrice
            if optionType == "CE":
                strikePrice = strikePrice - roundToNearestStrike
            else:
                strikePrice = strikePrice + roundToNearestStrike

        while True:
            try:
                symbol = prepareWeeklyOptionsSymbol(self.symbol, strikePrice, optionType, expiryDay=self.expiryDay)
                getInstrumentDataBySymbol(self.short_code, symbol)
                quote = self.getQuote(symbol)

                if quote.totalSellQuantity == 0 and quote.totalBuyQuantity == 0:
                    time.sleep(1)
                    quote = self.getQuote(symbol)  # lets try one more time.

                premium = quote.lastTradedPrice

                if premium < maximumPremium:
                    return strikePrice, premium

                lastStrike = strikePrice
                lastPremium = premium

                if optionType == "CE":
                    strikePrice = strikePrice + roundToNearestStrike
                else:
                    strikePrice = strikePrice - roundToNearestStrike
                time.sleep(1)
            except KeyError:
                return lastStrike, lastPremium

    def getVIXAdjustment(self, shortCode):
        return math.pow(symbolToCMPMap[shortCode]["INDIA VIX"] / 16, 0.5)

    def asDict(self):
        dict = {}
        dict["enabled"] = self.enabled
        dict["strategySL"] = self.strategySL
        dict["strategyTarget"] = self.strategyTarget
        return dict

    def fromDict(self, dict):
        if not dict is None:
            self.enabled = dict["enabled"]
            self.strategySL = dict["strategySL"]
            self.strategyTarget = dict["strategyTarget"]

    def _getLots(self, strategyName, symbol, expiryDay):
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


class StartTimedBaseStrategy(BaseStrategy):

    # DO NOT call the base constructor, as it will override the start time and register with trademanager with overridden timestamp
    def __init__(self, name, short_code, startTime, handler: BaseHandler, multiple=0) -> None:
        self.name = name  # strategy name
        self.short_code = short_code
        self.handler = handler
        self.enabled = True  # Strategy will be run only when it is enabled
        self.productType = ProductType.MIS  # MIS/NRML/CNC etc
        self.symbols = []  # List of stocks to be traded under this strategy
        self.slPercentage = 0
        self.targetPercentage = 0
        self.startTimestamp = startTime  # When to start the strategy. Default is Market start time
        self.stopTimestamp = None  # This is not square off timestamp. This is the timestamp after which no new trades will be placed under this strategy but existing trades continue to be active.
        self.squareOffTimestamp = None  # Square off time
        self.maxTradesPerDay = 1  # Max number of trades per day under this strategy
        self.isFnO = True  # Does this strategy trade in FnO or not
        self.strategySL = 0
        self.strategyTarget = 0
        self.trades: List[Trade] = []
        self.expiryDay = 2
        self.symbol = "BANKNIFTY"
        self.multiple = multiple
        self.exchange = "NFO"
        self.equityExchange = "NSE"

    def getName(self):
        return super().getName() + "_" + str(self.startTimestamp.time())
