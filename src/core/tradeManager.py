import logging
import os
import time
from typing import Any, Dict

from utils import getTodayDateStr, getUserDetails, waitTillMarketOpens

from broker import BaseTicker, brokers
from config import getServerConfig


class TradeManager:

    strategyToInstanceMap: Dict[str, Any] = {}
    symbolToCMPMap: Dict[str, float] = {}
    ticker: BaseTicker

    def __init__(self, short_code: str, access_token: str) -> None:
        self.short_code = short_code
        self.access_token = access_token
        serverConfig = getServerConfig()
        tradesDir = os.path.join(serverConfig["deployDir"], "trades")
        self.intradayTradesDir = os.path.join(tradesDir, getTodayDateStr())
        if os.path.exists(self.intradayTradesDir) == False:
            logging.info("TradeManager: Intraday Trades Directory %s does not exist. Hence going to create.", self.intradayTradesDir)
            os.makedirs(self.intradayTradesDir)

        self.ticker = brokers[getUserDetails(short_code).broker]["ticker"](short_code)

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

    def loadAllTradesFromFile(self):
        tradesFilepath = self.getTradesFilepath()
        if os.path.exists(tradesFilepath) == False:
            logging.warn("TradeManager: loadAllTradesFromFile() Trades Filepath %s does not exist", tradesFilepath)
            return
        self.trades = []
        tFile = open(tradesFilepath, "r")
        tradesData = json.loads(tFile.read())
        for tr in tradesData:
            trade = Utils.convertJSONToTrade(tr)
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
            logging.warn("TradeManager: loadAllTradesFromFile() Trades Filepath %s does not exist", strategiesFilePath)
            return
        sFile = open(strategiesFilePath, "r")
        self.strategiesData = json.loads(sFile.read())
        logging.info("TradeManager: Successfully loaded %d strategies from json file %s", len(self.strategiesData), strategiesFilePath)

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
        #                 longTrade.startTimestamp = Utils.getEpoch()
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
        #                 shortTrade.startTimestamp = Utils.getEpoch()
        #             else:
        #                 shortTrade.tradeState = TradeState.DISABLED
