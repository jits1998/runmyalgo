import asyncio
import logging
import math
import time
from abc import ABC
from datetime import datetime
from math import ceil
from typing import Dict, List

from broker.base import BaseHandler
from core import Quote
from exceptions import DeRegisterStrategyException, DisableTradeException
from instruments import getCMP, getInstrumentDataBySymbol, roundToNSEPrice
from models import (
    Direction,
    OrderStatus,
    OrderType,
    ProductType,
    TradeExitReason,
    TradeState,
)
from models.trade import Trade
from utils import (
    calculateTradePnl,
    findNumberOfDaysBeforeWeeklyExpiryDay,
    getEpoch,
    getMarketStartTime,
    getNearestStrikePrice,
    getTimeOfToDay,
    isMarketClosedForTheDay,
    isTodayWeeklyExpiryDay,
    prepareMonthlyExpiryFuturesSymbol,
    prepareWeeklyOptionsSymbol,
    waitTillMarketOpens,
)


class BaseStrategy(ABC):

    def __init__(self, name: str, short_code: str, handler: BaseHandler, multiple: int = 0) -> None:  # type: ignore
        # NOTE: All the below properties should be set by the Derived Class (Specific to each strategy)
        self.name = name  # strategy name
        self.short_code = short_code
        self.orderQueue: asyncio.Queue[Trade]
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

    async def run(self, runConfig):

        self.runConfig = runConfig  # store run from algo config to getLots later

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

            # track each trade and take necessary action
            self.trackAndUpdateAllTrades()

            self.checkStrategyHealth()

            # Derived class specific implementation will be called when process() is called
            await self.process()

            # Sleep and wake up 5s after every 15th second, ie after trade manager has updated trades

            waitSeconds = 5 - (now.second % 5) + 3
            await asyncio.sleep(waitSeconds)

    def trackAndUpdateAllTrades(self):

        for trade in self.trades:
            if trade.tradeState == TradeState.ACTIVE:
                self._trackEntryOrder(trade)
                self._trackTargetOrder(trade)
                self._trackSLOrder(trade)
                if trade.intradaySquareOffTimestamp != None:
                    nowEpoch = getEpoch()
                    if nowEpoch >= trade.intradaySquareOffTimestamp:
                        trade.target = getCMP(self.short_code, trade.tradingSymbol)
                        self.squareOffTrade(trade, TradeExitReason.SQUARE_OFF)

    def _trackEntryOrder(self, trade):
        if trade.tradeState != TradeState.ACTIVE:
            return

        if len(trade.entryOrder) == 0:
            return

        trade.filledQty = 0
        trade.entry = 0
        orderCanceled = 0
        orderRejected = 0

        for entryOrder in trade.entryOrder:
            if entryOrder.orderStatus == OrderStatus.CANCELLED:
                orderCanceled += 1

            if entryOrder.orderStatus == entryOrder.orderStatus == OrderStatus.REJECTED:
                orderRejected += 1

            if entryOrder.filledQty > 0:
                trade.entry = (trade.entry * trade.filledQty + entryOrder.averagePrice * entryOrder.filledQty) / (trade.filledQty + entryOrder.filledQty)
            elif entryOrder.orderStatus not in [OrderStatus.REJECTED, OrderStatus.CANCELLED, None] and not entryOrder.orderType in [OrderType.SL_LIMIT]:
                omp = OrderModifyParams()
                if trade.direction == Direction.LONG:
                    omp.newPrice = roundToNSEPrice(entryOrder.price * 1.01) + 0.05
                else:
                    omp.newPrice = roundToNSEPrice(entryOrder.price * 0.99) - 0.05
                try:
                    self.modifyOrder(entryOrder, omp, trade.qty)
                except Exception as e:
                    if e.args[0] == "Maximum allowed order modifications exceeded.":
                        self.cancelOrder(entryOrder)
            elif entryOrder.orderStatus in [OrderStatus.TRIGGER_PENDING]:
                nowEpoch = getEpoch()
                if nowEpoch >= getEpoch(self.strategyToInstanceMap[trade.strategy].stopTimestamp):
                    self.cancelOrder(entryOrder)

            trade.filledQty += entryOrder.filledQty

        if orderCanceled == len(trade.entryOrder):
            trade.tradeState = TradeState.CANCELLED

        if orderRejected == len(trade.entryOrder):
            trade.tradeState = TradeState.DISABLED

        if orderRejected > 0:
            strategy = self.strategyToInstanceMap[trade.strategy]
            for trade in strategy.trades:
                if trade.tradeState in (TradeState.ACTIVE):
                    trade.target = getCMP(self.short_code, trade.tradingSymbol)
                    self.squareOffTrade(trade, TradeExitReason.TRADE_FAILED)
                strategy.setDisabled()

        # Update the current market price and calculate pnl
        trade.cmp = getCMP(self.short_code, trade.tradingSymbol)
        calculateTradePnl(trade)

    def _trackSLOrder(self, trade):
        if trade.tradeState != TradeState.ACTIVE:
            for entryOrder in trade.entryOrder:
                if entryOrder.orderStatus in [OrderStatus.OPEN, OrderStatus.TRIGGER_PENDING]:
                    return
        if trade.stopLoss == 0:
            # check if stoploss is yet to be calculated
            newSL = self.strategyToInstanceMap.get(trade.strategy, None).getTrailingSL(trade)
            if newSL == 0:
                return
            else:
                trade.stopLoss = newSL

        if len(trade.slOrder) == 0 and trade.entry > 0:
            # Place SL order
            self.placeSLOrder(trade)
        else:
            slCompleted = 0
            slAverage = 0
            slQuantity = 0
            slCancelled = 0
            slRejected = 0
            slOpen = 0
            for slOrder in trade.slOrder:
                if slOrder.orderStatus == OrderStatus.COMPLETE:
                    slCompleted += 1
                    slAverage = (slQuantity * slAverage + slOrder.filledQty * slOrder.averagePrice) / (slQuantity + slOrder.filledQty)
                    slQuantity += slOrder.filledQty
                elif slOrder.orderStatus == OrderStatus.CANCELLED:
                    slCancelled += 1
                elif slOrder.orderStatus == OrderStatus.REJECTED:
                    slRejected += 1
                elif slOrder.orderStatus == OrderStatus.OPEN:
                    slOpen += 1
                    newPrice = (slOrder.price + getCMP(self.short_code, trade.tradingSymbol)) * 0.5
                    omp = OrderModifyParams()
                    if trade.direction == Direction.LONG:
                        omp.newTriggerPrice = roundToNSEPrice(newPrice) - 0.05
                        omp.newPrice = roundToNSEPrice(newPrice * 0.99) - 0.05
                    else:
                        omp.newTriggerPrice = roundToNSEPrice(newPrice) + 0.05
                        omp.newPrice = roundToNSEPrice(newPrice * 1.01) + 0.05

                    self.modifyOrder(slOrder, omp, trade.qty)

            if slCompleted == len(trade.slOrder) and len(trade.slOrder) > 0:
                # SL Hit
                exit = slAverage
                exitReason = TradeExitReason.SL_HIT if trade.initialStopLoss == trade.stopLoss else TradeExitReason.TRAIL_SL_HIT
                self.setTradeToCompleted(trade, exit, exitReason)
                # Make sure to cancel target order if exists
                self.cancelOrders(trade.targetOrder)

            elif slCancelled == len(trade.slOrder) and len(trade.slOrder) > 0:
                targetOrderPendingCount = 0
                for targetOrder in trade.targetOrder:
                    if targetOrder.orderStatus not in [OrderStatus.COMPLETE, OrderStatus.OPEN]:
                        targetOrderPendingCount += 1
                if targetOrderPendingCount == len(trade.targetOrder):
                    # Cancel target order if exists
                    self.cancelOrders(trade.targetOrder)
                    # SL order cancelled outside of algo (manually or by broker or by exchange)
                    logging.error(
                        "SL order tradeID %s cancelled outside of Algo. Setting the trade as completed with exit price as current market price.", trade.tradeID
                    )
                    exit = getCMP(self.short_code, trade.tradingSymbol)
                    self.setTradeToCompleted(trade, exit, TradeExitReason.SL_CANCELLED)
            elif slRejected > 0:
                strategy = self.strategyToInstanceMap[trade.strategy]
                for trade in strategy.trades:
                    if trade.tradeState in (TradeState.ACTIVE):
                        trade.target = getCMP(self.short_code, trade.tradingSymbol)
                        self.squareOffTrade(trade, TradeExitReason.TRADE_FAILED)
                    strategy.setDisabled()
            elif slOpen > 0:
                pass  # handled above, skip calling trail SL
            else:
                self.checkAndUpdateTrailSL(trade)

    def checkAndUpdateTrailSL(self, trade):
        # Trail the SL if applicable for the trade
        strategyInstance = self
        newTrailSL = roundToNSEPrice(strategyInstance.getTrailingSL(trade))
        updateSL = False
        if newTrailSL > 0:
            if trade.direction == Direction.LONG and newTrailSL > trade.stopLoss:
                if newTrailSL < trade.cmp:
                    updateSL = True
                else:
                    logging.info("TradeManager: Trail SL %f triggered Squareoff at market for tradeID %s", newTrailSL, trade.tradeID)
                    self.squareOffTrade(trade, reason=TradeExitReason.SL_HIT)
            elif trade.direction == Direction.SHORT and newTrailSL < trade.stopLoss:
                if newTrailSL > trade.cmp:
                    updateSL = True
                else:  # in case the SL is called due to all leg squareoff
                    logging.info("TradeManager: Trail SL %f triggered Squareoff at market for tradeID %s", newTrailSL, trade.tradeID)
                    self.squareOffTrade(trade, reason=TradeExitReason.SL_HIT)
        if updateSL == True:
            omp = OrderModifyParams()
            omp.newTriggerPrice = newTrailSL
            omp.newPrice = roundToNSEPrice(omp.newTriggerPrice * (0.99 if trade.direction == Direction.LONG else 1.01))  # sl order direction is reverse
            try:
                oldSL = trade.stopLoss
                for slOrder in trade.slOrder:
                    self.modifyOrder(slOrder, omp, trade.qty)
                logging.info("TradeManager: Trail SL: Successfully modified stopLoss from %f to %f for tradeID %s", oldSL, newTrailSL, trade.tradeID)
                # IMPORTANT: Dont forget to update this on successful modification
                trade.stopLoss = newTrailSL
            except Exception as e:
                logging.error("TradeManager: Failed to modify SL order for tradeID %s : Error => %s", trade.tradeID, str(e))

    def _trackTargetOrder(self, trade):
        if trade.tradeState != TradeState.ACTIVE and self.strategyToInstanceMap[trade.strategy].isTargetORSLHit() is not None:
            return
        if trade.target == 0:  # Do not place Target order if no target provided
            return
        if len(trade.targetOrder) == 0 and trade.entry > 0:  # place target order only after the entry happened
            # Place Target order
            self.placeTargetOrder(trade)
        else:
            targetCompleted = 0
            targetAverage = 0
            targetQuantity = 0
            targetCancelled = 0
            targetOpen = 0
            for targetOrder in trade.targetOrder:
                if targetOrder.orderStatus == OrderStatus.COMPLETE:
                    targetCompleted += 1
                    targetAverage = (targetQuantity * targetAverage + targetOrder.filledQty * targetOrder.averagePrice) / (
                        targetQuantity + targetOrder.filledQty
                    )
                    targetQuantity += targetOrder.filledQty
                elif targetOrder.orderStatus == OrderStatus.CANCELLED:
                    targetCancelled += 1
                elif targetOrder.orderStatus == OrderStatus.OPEN and trade.exitReason is not None:
                    targetOpen += 1
                    omp = OrderModifyParams()
                    if trade.direction == Direction.LONG:
                        omp.newTriggerPrice = roundToNSEPrice(targetOrder.price * 0.99) - 0.05
                        omp.newPrice = roundToNSEPrice(omp.newTriggerPrice * 0.99) - 0.05
                    else:
                        omp.newTriggerPrice = roundToNSEPrice(targetOrder.price * 1.01) + 0.05
                        omp.newPrice = roundToNSEPrice(omp.newTriggerPrice * 1.01) + 0.05

                    self.modifyOrder(targetOrder, omp, trade.qty)

            if targetCompleted == len(trade.targetOrder) and len(trade.targetOrder) > 0:
                # Target Hit
                exit = targetAverage
                self.setTradeToCompleted(trade, exit, TradeExitReason.TARGET_HIT)
                # Make sure to cancel sl order
                self.cancelOrders(trade.slOrder)

            elif targetCancelled == len(trade.targetOrder) and len(trade.targetOrder) > 0:
                # Target order cancelled outside of algo (manually or by broker or by exchange)
                logging.error(
                    "Target orderfor tradeID %s cancelled outside of Algo. Setting the trade as completed with exit price as current market price.",
                    trade.tradeID,
                )
                exit = getCMP(self.short_code, trade.tradingSymbol)
                self.setTradeToCompleted(trade, exit, TradeExitReason.TARGET_CANCELLED)
                # Cancel SL order
                self.cancelOrders(trade.slOrder)

    def cancelOrders(self, orders):
        if len(orders) == 0:
            return
        for order in orders:
            if order.orderStatus == OrderStatus.CANCELLED:
                continue
            try:
                self.cancelOrder(order)
            except Exception as e:
                logging.error("TradeManager: Failed to cancel order %s: Error => %s", order.orderId, str(e))
                raise (e)
            logging.info("TradeManager: Successfully cancelled order %s", order.orderId)

    def cancelOrder(self, order):
        pass

    def modifyOrder(self, order, omp, qty):
        pass

    def setTradeToCompleted(self, trade, exit, exitReason=None):
        trade.tradeState = TradeState.COMPLETED
        trade.exit = exit
        trade.exitReason = exitReason if trade.exitReason == None else trade.exitReason
        # TODO Timestamp to be matched with last order
        # if trade.targetOrder != None and trade.targetOrder.orderStatus == OrderStatus.COMPLETE:
        #     trade.endTimestamp = datetime.strptime(
        #         trade.targetOrder.lastOrderUpdateTimestamp, "%Y-%m-%d %H:%M:%S").timestamp()
        # elif trade.slOrder != None and trade.slOrder.orderStatus == OrderStatus.COMPLETE:
        #     trade.endTimestamp = datetime.strptime(
        #         trade.slOrder.lastOrderUpdateTimestamp, "%Y-%m-%d %H:%M:%S").timestamp()
        # else:
        trade.endTimestamp = getEpoch()

        trade = calculateTradePnl(trade)

    def squareOffTrade(self, trade, reason=TradeExitReason.SQUARE_OFF):
        logging.info("TradeManager: squareOffTrade called for tradeID %s with reason %s", trade.tradeID, reason)
        if trade == None or trade.tradeState != TradeState.ACTIVE:
            return

        trade.exitReason = reason
        if len(trade.entryOrder) > 0:
            for entryOrder in trade.entryOrder:
                if entryOrder.orderStatus in [OrderStatus.OPEN, OrderStatus.TRIGGER_PENDING]:
                    # Cancel entry order if it is still open (not filled or partially filled case)
                    self.cancelOrders(trade.entryOrder)
                    break

        if len(trade.slOrder) > 0:
            try:
                self.cancelOrders(trade.slOrder)
            except Exception:
                # probably the order is being processed.
                logging.info(
                    "TradeManager: squareOffTrade couldn't cancel SL order for %s, not placing target order, strategy will be disabled", trade.tradeID
                )
                return

        if len(trade.targetOrder) > 0:
            # Change target order type to MARKET to exit position immediately
            logging.info("TradeManager: changing target order to closer to MARKET to exit tradeID %s", trade.tradeID)
            for targetOrder in trade.targetOrder:
                if targetOrder.orderStatus == OrderStatus.OPEN:
                    omp = OrderModifyParams()
                    omp.newPrice = roundToNSEPrice(trade.cmp * (0.99 if trade.direction == Direction.LONG else 1.01))
                    self.modifyOrder(targetOrder, omp, trade.filledQty)
        elif trade.entry > 0:
            # Place new target order to exit position, adjust target to current market price
            logging.info("TradeManager: placing new target order to exit position for tradeID %s", trade.tradeID)
            self.placeTargetOrder(trade, True, targetPrice=(trade.cmp * (0.99 if trade.direction == Direction.LONG else 1.01)))

    def shouldPlaceTrade(self, trade):
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

    async def generateTrade(self, optionSymbol, direction, numLots, lastTradedPrice, slPercentage=0, slPrice=0, targetPrice=0, placeMarketOrder=True):
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
        await self.orderQueue.put(trade)

    async def generateTradeWithSLPrice(
        self, optionSymbol, direction, numLots, lastTradedPrice, underLying, underLyingStopLossPercentage, placeMarketOrder=True
    ):
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
        await self.orderQueue.put(trade)

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
        return math.pow(getCMP(self.short_code, "INDIA VIX") / 16, 0.5)

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
        strategyLots = self.runConfig
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


class ManualStrategy(BaseStrategy):

    __instance: Dict[str, BaseStrategy] = {}

    @staticmethod
    def getInstance(short_code):  # singleton class
        if ManualStrategy.__instance.get(short_code, None) == None:
            ManualStrategy(short_code)
        return ManualStrategy.__instance[short_code]

    def __init__(self, short_code: str, handler: BaseHandler, multiple: int = 0):

        if ManualStrategy.__instance.get(short_code, None) != None:
            raise Exception("This class is a singleton!")
        else:
            ManualStrategy.__instance[short_code] = self

        super().__init__("ManualStrategy", short_code, handler, multiple)  # type: ignore

        # When to start the strategy. Default is Market start time
        self.startTimestamp = getTimeOfToDay(9, 16, 0)
        self.productType = ProductType.MIS
        # This is not square off timestamp. This is the timestamp after which no new trades will be placed under this strategy but existing trades continue to be active.
        self.stopTimestamp = getTimeOfToDay(15, 24, 0)
        self.squareOffTimestamp = getTimeOfToDay(15, 24, 0)  # Square off time
        self.maxTradesPerDay = 10

    async def process(self):
        now = datetime.now()
        if now < self.startTimestamp or not self.isEnabled():
            return


class TestStrategy(BaseStrategy):
    __instance: Dict[str, BaseStrategy] = {}

    @staticmethod
    def getInstance(short_code):  # singleton class
        if TestStrategy.__instance.get(short_code, None) == None:
            TestStrategy()
        return TestStrategy.__instance[short_code]

    def __init__(self, short_code: str, handler: BaseHandler, multiple: int = 0):
        if TestStrategy.__instance.get(short_code, None) != None:
            raise Exception("This class is a singleton!")
        else:
            TestStrategy.__instance[short_code] = self
        # Call Base class constructor
        super().__init__("TestStrategy", short_code, multiple)  # type: ignore
        # Initialize all the properties specific to this strategy
        self.productType = ProductType.MIS
        self.symbols = []
        self.slPercentage = 0
        self.targetPercentage = 0
        self.startTimestamp = getTimeOfToDay(9, 25, 0)  # When to start the strategy. Default is Market start time
        self.stopTimestamp = getTimeOfToDay(
            15, 15, 0
        )  # This is not square off timestamp. This is the timestamp after which no new trades will be placed under this strategy but existing trades continue to be active.
        self.squareOffTimestamp = getTimeOfToDay(15, 15, 0)  # Square off time
        self.maxTradesPerDay = 2  # (1 CE + 1 PE) Max number of trades per day under this strategy
        self.ceTrades = []
        self.peTrades = []
        self.strategyTarget = 2000
        self.strategySL = -1000
        self.symbol = "NIFTY"
        self.expiryDay = 3

        for trade in self.trades:
            if trade.tradingSymbol.endswith("CE"):
                self.ceTrades.append(trade)
            else:
                self.peTrades.append(trade)

    async def process(self):
        now = datetime.now()
        if now < self.startTimestamp or not self.isEnabled():
            return

        if len(self.ceTrades) >= 1 and len(self.peTrades) >= 1:
            return

        if self.isTargetORSLHit():
            # self.setDisabled()
            return
        indexSymbol = "NIFTY 50"
        # Get current market price of Nifty Future
        quote = self.handler.getIndexQuote(indexSymbol, self.short_code)
        if quote == None:
            logging.error("%s: Could not get quote for %s", self.getName(), indexSymbol)
            return

        ATMStrike = getNearestStrikePrice(quote.lastTradedPrice, 50)

        ATMCESymbol = prepareWeeklyOptionsSymbol(self.symbol, ATMStrike, "CE", expiryDay=self.expiryDay)
        ATMCEQuote = self.getQuote(ATMCESymbol).lastTradedPrice

        ATMPESymbol = prepareWeeklyOptionsSymbol(self.symbol, ATMStrike, "PE", expiryDay=self.expiryDay)
        ATMPEQuote = self.getQuote(ATMPESymbol).lastTradedPrice

        OTMPEStrike = getNearestStrikePrice(quote.lastTradedPrice - 500, 50)
        OTMPESymbol = prepareWeeklyOptionsSymbol(self.symbol, OTMPEStrike, "PE", expiryDay=self.expiryDay)
        OTMPEQuote = self.getQuote(OTMPESymbol).lastTradedPrice

        OTMCEStrike = getNearestStrikePrice(quote.lastTradedPrice + 500, 50)
        OTMCESymbol = prepareWeeklyOptionsSymbol(self.symbol, OTMCEStrike, "CE", expiryDay=self.expiryDay)
        OTMCEQuote = self.getQuote(OTMCESymbol).lastTradedPrice

        # self.generateTrade(OTMPESymbol, Direction.SHORT, self.getLots(), OTMPEQuote * 1.2, 5)
        await self.generateTrade(OTMCESymbol, Direction.SHORT, self.getLots(), OTMCEQuote * 1.2, 5)

    def shouldPlaceTrade(self, trade: Trade):
        if not super().shouldPlaceTrade(trade):
            return False
        if (trade.tradingSymbol.endswith("CE")) and len(self.ceTrades) < 2:
            return True
        if (trade.tradingSymbol.endswith("PE")) and len(self.peTrades) < 2:
            return True

        return False

    def addTradeToList(self, trade: Trade):
        if trade != None:
            self.trades.append(trade)
            if trade.tradingSymbol.endswith("CE"):
                self.ceTrades.append(trade)
            else:
                self.peTrades.append(trade)

    def getTrailingSL(self, trade: Trade):

        if trade.stopLoss == 0 and trade.entry > 0:
            trade.initialStopLoss = roundToNSEPrice(self.short_code, trade.tradingSymbol, trade.entry + (+1 if trade.direction == Direction.SHORT else -1) * 1)
            return trade.initialStopLoss

        trailSL = 0
        return trailSL
