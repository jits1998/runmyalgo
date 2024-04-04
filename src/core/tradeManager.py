from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import traceback
from datetime import datetime
from json import JSONEncoder
from typing import Any, Dict, List

import psycopg2

from broker import BaseHandler, BaseTicker, brokers
from config import getServerConfig
from core.strategy import BaseStrategy
from instruments import roundToNSEPrice
from instruments import symbolToCMPMap as cmp
from models import Direction, OrderType, TradeState
from models.order import Order, OrderInputParams
from models.trade import Trade
from utils import (
    getEpoch,
    getTodayDateStr,
    getUserDetails,
    isMarketClosedForTheDay,
    isTodayHoliday,
    waitTillMarketOpens,
)


class TradeEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        if isinstance(o, (BaseStrategy)):
            return o.asDict()
        return o.__dict__


class TradeManager:

    strategyToInstanceMap: Dict[str, BaseStrategy] = {}
    symbolToCMPMap: Dict[str, float] = {}
    ticker: BaseTicker

    def __init__(self, short_code: str, access_token: str, brokerHandler: BaseHandler) -> None:
        self.short_code = short_code
        self.access_token = access_token
        self.symbolToCMPMap = cmp[short_code]
        self.orderQueue: asyncio.Queue[Trade] = asyncio.Queue()
        self.questDBCursor = self.getQuestDBConnection()
        self.strategiesData: Dict[str, Any] = {}
        self.trades: List[Trade] = []

        serverConfig = getServerConfig()
        tradesDir = os.path.join(serverConfig["deployDir"], "trades")
        self.intradayTradesDir = os.path.join(tradesDir, getTodayDateStr())
        if os.path.exists(self.intradayTradesDir) == False:
            logging.info("TradeManager: Intraday Trades Directory %s does not exist. Hence going to create.", self.intradayTradesDir)
            os.makedirs(self.intradayTradesDir)

        self.order_manager = brokers[getUserDetails(short_code).broker]["order_manager"](short_code, brokerHandler)

        self.ticker = brokers[getUserDetails(short_code).broker]["ticker"](short_code, brokerHandler)

        self.ticker.startTicker(getUserDetails(short_code).key, self.access_token)
        self.ticker.registerListener(self.tickerListener)

        self.ticker.registerSymbols(["NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY FIN SERVICE"])

        # Load all trades from json files to app memory
        self.loadAllTradesFromFile()
        self.loadAllStrategiesFromFile()

        # sleep for 2 seconds for ticker to update ltp map
        time.sleep(2)

        self.isReady = True

        waitTillMarketOpens("TradeManager")

    async def run(self):  # track and update trades in a loop
        while True:

            if self.questDBCursor is None or self.questDBCursor.closed:
                self.questDBCursor = self.getQuestDBConnection()

            if not isTodayHoliday() and not isMarketClosedForTheDay() and not len(self.strategyToInstanceMap) == 0:
                try:
                    # Fetch all order details from broker and update orders in each trade
                    self.fetchAndUpdateAllTradeOrders()
                    # track each trade and take necessary action
                    self.trackAndUpdateAllTrades()

                    self.checkStrategyHealth()
                    # print ( "%s =>%f :: %f" %(datetime.now().strftime("%H:%M:%S"), pe_vega, ce_vega))
                except Exception as e:
                    traceback.print_exc()
                    logging.exception("Exception in TradeManager Main thread")

                # save updated data to json file
                self.saveAllTradesToFile()
                self.saveAllStrategiesToFile()

            now = datetime.now()
            waitSeconds = 5 - (now.second % 5)
            await asyncio.sleep(waitSeconds)

    def squareOffTrade(self, trade, exitReason):
        pass

    def squareOffStrategy(self, strategyInstance, exitReason):
        pass

    async def placeOrders(self):
        while True:
            trade: Trade = await self.orderQueue.get()  # type: ignore
            try:
                strategyInstance = self.strategyToInstanceMap[trade.strategy]
                if strategyInstance.shouldPlaceTrade(trade):
                    # place the longTrade
                    isSuccess = self.executeTrade(trade)
                    if isSuccess == True:
                        # set longTrade state to ACTIVE
                        trade.tradeState = TradeState.ACTIVE
                        trade.startTimestamp = getEpoch()
                        continue
            except Exception as e:
                logging.warn(str(e))

            trade.tradeState = TradeState.DISABLED

    def executeTrade(self, trade):
        logging.info("TradeManager: Execute trade called for %s", trade)
        trade.initialStopLoss = trade.stopLoss
        # Create order input params object and place order
        oip = OrderInputParams(trade.tradingSymbol)
        oip.exchange = trade.exchange
        oip.direction = trade.direction
        oip.productType = trade.productType
        oip.orderType = OrderType.LIMIT if trade.placeMarketOrder == True else OrderType.SL_LIMIT
        oip.triggerPrice = roundToNSEPrice(trade.requestedEntry)
        oip.price = roundToNSEPrice(self.short_code, trade.tradingSymbol, trade.requestedEntry * (1.01 if trade.direction == Direction.LONG else 0.99))
        oip.qty = trade.qty
        oip.tag = trade.strategy
        if trade.isFutures == True or trade.isOptions == True:
            oip.isFnO = True
        try:
            placedOrder = self.order_manager.placeOrder(oip)
            trade.entryOrder.append(placedOrder)
            self.orders[placedOrder.orderId] = placedOrder
        except Exception as e:
            logging.error("TradeManager: Execute trade failed for tradeID %s: Error => %s", trade.tradeID, str(e))
            return False

        logging.info("TradeManager: Execute trade successful for %s and entryOrder %s", trade, trade.entryOrder)
        return True

    def registerStrategy(self, strategyInstance):
        self.strategyToInstanceMap[strategyInstance.getName()] = strategyInstance
        strategyInstance.strategyData = self.strategiesData.get(strategyInstance.getName(), None)
        strategyInstance.orderQueue = self.orderQueue

    def deRgisterStrategy(self, strategyInstanceName):
        del self.strategyToInstanceMap[strategyInstanceName]

    def loadAllTradesFromFile(self):
        tradesFilepath = self.getTradesFilepath()
        if os.path.exists(tradesFilepath) == False:
            logging.warn("TradeManager: loadAllTradesFromFile() Trades Filepath %s does not exist", tradesFilepath)
            return
        self.trades = []
        tFile = open(tradesFilepath, "r")
        tradesData = json.loads(tFile.read())
        for tr in tradesData:
            trade = self.convertJSONToTrade(tr)
            logging.info("loadAllTradesFromFile trade => %s", trade)
            self.trades.append(trade)
            if trade.tradingSymbol not in self.registeredSymbols:
                # Algo register symbols with ticker
                self.ticker.registerSymbols([trade.tradingSymbol])
                self.registeredSymbols.append(trade.tradingSymbol)
        logging.info("TradeManager: Successfully loaded %d trades from json file %s", len(self.trades), tradesFilepath)

    def loadAllStrategiesFromFile(self):
        strategiesFilePath = self.getStrategiesFilepath()
        if os.path.exists(strategiesFilePath) == False:
            logging.warn("TradeManager: loadAllStrategiesFromFile() STrategies Filepath %s does not exist", strategiesFilePath)
            return
        sFile = open(strategiesFilePath, "r")
        self.strategiesData = json.loads(sFile.read())
        logging.info("TradeManager: Successfully loaded %d strategies from json file %s", len(self.strategiesData), strategiesFilePath)

    def getTradesFilepath(self):
        tradesFilepath = os.path.join(
            self.intradayTradesDir, getUserDetails(self.short_code).broker + "_" + getUserDetails(self.short_code).clientID + ".json"
        )
        return tradesFilepath

    def getStrategiesFilepath(self):
        tradesFilepath = os.path.join(
            self.intradayTradesDir, getUserDetails(self.short_code).broker + "_" + getUserDetails(self.short_code).clientID + "_strategies.json"
        )
        return tradesFilepath

    def saveAllTradesToFile(self):
        tradesFilepath = self.getTradesFilepath()
        with open(tradesFilepath, "w") as tFile:
            json.dump(self.trades, tFile, indent=2, cls=TradeEncoder)
        logging.debug("TradeManager: Saved %d trades to file %s", len(self.trades), tradesFilepath)

    def saveAllStrategiesToFile(self):
        strategiesFilePath = self.getStrategiesFilepath()
        with open(strategiesFilePath, "w") as tFile:
            json.dump(self.strategyToInstanceMap, tFile, indent=2, cls=TradeEncoder)
        logging.debug("TradeManager: Saved %d strategies to file %s", len(self.strategyToInstanceMap.values()), strategiesFilePath)

    def getAllTradesByStrategy(self, strategy: str):
        tradesByStrategy = []
        for trade in self.trades:
            if trade.strategy == strategy:
                tradesByStrategy.append(trade)
        return tradesByStrategy

    def getQuestDBConnection(self):
        try:
            connection = psycopg2.connect(user="admin", password="quest", host="127.0.0.1", port="8812", database="qdb")
            cursor = connection.cursor()

            cursor.execute(
                """CREATE TABLE IF NOT EXISTS {0} ( ts TIMESTAMP, strategy string, tradingSymbol string, tradeId string, cmp float, entry float, pnl float, qty int, status string) timestamp(ts) partition by year""".format(
                    self.short_code
                )
            )
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS {0}_tickData( ts TIMESTAMP, tradingSymbol string, ltp float, qty int, avgPrice float, volume int, totalBuyQuantity int, totalSellQuantity int, open float, high float, low float, close float, change float) timestamp(ts) partition by year""".format(
                    self.short_code
                )
            )

            logging.info("Connected to Quest DB")
            return cursor
        except Exception as err:
            logging.info("Can't connect to QuestDB")
            return None

    def convertJSONToOrder(self, jsonData):
        if jsonData == None:
            return None
        order = Order()
        order.tradingSymbol = jsonData["tradingSymbol"]
        order.exchange = jsonData["exchange"]
        order.productType = jsonData["productType"]
        order.orderType = jsonData["orderType"]
        order.price = jsonData["price"]
        order.triggerPrice = jsonData["triggerPrice"]
        order.qty = jsonData["qty"]
        order.orderId = jsonData["orderId"]
        order.orderStatus = jsonData["orderStatus"]
        order.averagePrice = jsonData["averagePrice"]
        order.filledQty = jsonData["filledQty"]
        order.pendingQty = jsonData["pendingQty"]
        order.orderPlaceTimestamp = jsonData["orderPlaceTimestamp"]
        order.lastOrderUpdateTimestamp = jsonData["lastOrderUpdateTimestamp"]
        order.message = jsonData["message"]
        order.parentOrderId = jsonData.get("parent_order_id", "")
        return order

    def convertJSONToTrade(self, jsonData):
        trade = Trade(jsonData["tradingSymbol"])
        trade.tradeID = jsonData["tradeID"]
        trade.strategy = jsonData["strategy"]
        trade.direction = jsonData["direction"]
        trade.productType = jsonData["productType"]
        trade.isFutures = jsonData["isFutures"]
        trade.isOptions = jsonData["isOptions"]
        trade.optionType = jsonData["optionType"]
        trade.underLying = jsonData.get("underLying", "")
        trade.placeMarketOrder = jsonData["placeMarketOrder"]
        trade.intradaySquareOffTimestamp = jsonData["intradaySquareOffTimestamp"]
        trade.requestedEntry = jsonData["requestedEntry"]
        trade.entry = jsonData["entry"]
        trade.qty = jsonData["qty"]
        trade.filledQty = jsonData["filledQty"]
        trade.initialStopLoss = jsonData["initialStopLoss"]
        trade.stopLoss = jsonData["_stopLoss"]
        trade.stopLossPercentage = jsonData.get("stopLossPercentage", 0)
        trade.stopLossUnderlyingPercentage = jsonData.get("stopLossUnderlyingPercentage", 0)
        trade.target = jsonData["target"]
        trade.cmp = jsonData["cmp"]
        trade.tradeState = jsonData["tradeState"]
        trade.timestamp = jsonData["timestamp"]
        trade.createTimestamp = jsonData["createTimestamp"]
        trade.startTimestamp = jsonData["startTimestamp"]
        trade.endTimestamp = jsonData["endTimestamp"]
        trade.pnl = jsonData["pnl"]
        trade.pnlPercentage = jsonData["pnlPercentage"]
        trade.exit = jsonData["exit"]
        trade.exitReason = jsonData["exitReason"]
        trade.exchange = jsonData["exchange"]
        for entryOrder in jsonData["entryOrder"]:
            trade.entryOrder.append(self.convertJSONToOrder(entryOrder))
        for slOrder in jsonData["slOrder"]:
            trade.slOrder.append(self.convertJSONToOrder(slOrder))
        for trargetOrder in jsonData["targetOrder"]:
            trade.targetOrder.append(self.convertJSONToOrder(trargetOrder))

    def tickerListener(self, tick):
        # logging.info('tickerLister: new tick received for %s = %f', tick.tradingSymbol, tick.lastTradedPrice);
        # Store the latest tick in map
        self.symbolToCMPMap[tick.tradingSymbol] = tick.lastTradedPrice
        if tick.exchange_timestamp:
            self.symbolToCMPMap["exchange_timestamp"] = tick.exchange_timestamp
        # # On each new tick, get a created trade and call its strategy whether to place trade or not
        # for strategy in self.strategyToInstanceMap:
        #     longTrade = self.getUntriggeredTrade(tick.tradingSymbol, strategy, Direction.LONG)
        #     shortTrade = self.getUntriggeredTrade(tick.tradingSymbol, strategy, Direction.SHORT)
        #     if longTrade == None and shortTrade == None:
        #         continue
        #     strategyInstance = self.strategyToInstanceMap[strategy]
        #     if longTrade != None:
        #         if strategyInstance.shouldPlaceTrade(longTrade, tick):
        #             # place the longTrade
        #             isSuccess = self.executeTrade(longTrade)
        #             if isSuccess == True:
        #                 # set longTrade state to ACTIVE
        #                 longTrade.tradeState = TradeState.ACTIVE
        #                 longTrade.startTimestamp = getEpoch()
        #                 continue
        #             else:
        #                 longTrade.tradeState = TradeState.DISABLED

        #     if shortTrade != None:
        #         if strategyInstance.shouldPlaceTrade(shortTrade, tick):
        #             # place the shortTrade
        #             isSuccess = self.executeTrade(shortTrade)
        #             if isSuccess == True:
        #                 # set shortTrade state to ACTIVE
        #                 shortTrade.tradeState = TradeState.ACTIVE
        #                 shortTrade.startTimestamp = getEpoch()
        #             else:
        #                 shortTrade.tradeState = TradeState.DISABLED
