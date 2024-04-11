from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
import traceback
from json import JSONEncoder
from typing import Any, Dict, List

import psycopg2  # type: ignore

from broker import BaseHandler, BaseTicker, brokers
from config import get_server_config
from core.strategy import BaseStrategy
from instruments import round_to_ticksize
from instruments import symbol_to_CMP as cmp
from models import Direction, OrderType, TradeState
from models.order import Order, OrderInputParams
from models.trade import Trade
from utils import (
    get_epoch,
    get_today_date_str,
    get_user_details,
    is_market_closed_for_the_day,
    is_today_holiday,
    wait_till_market_open,
)


class TradeEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        if isinstance(o, (BaseStrategy)):
            return o.asDict()
        return o.__dict__


class TradeManager:

    strategy_to_instance: Dict[str, BaseStrategy] = {}
    symbol_to_cmp: Dict[str, float] = {}
    ticker: BaseTicker

    def __init__(self, short_code: str, access_token: str, broker_handler: BaseHandler) -> None:
        self.short_code = short_code
        self.access_token = access_token
        self.symbol_to_cmp = cmp[short_code]
        self.order_queue: asyncio.Queue[Trade] = asyncio.Queue()
        self.questDBCursor = self.get_questdb_connection()
        self.strategies_data: Dict[str, Any] = {}
        self.trades: List[Trade] = []
        self.orders: Dict[str, Order] = {}

        server_config = get_server_config()
        trades_dir = os.path.join(server_config["deploy_dir"], "trades")
        self.intradayTradesDir = os.path.join(trades_dir, get_today_date_str())
        if os.path.exists(self.intradayTradesDir) == False:
            logging.info("TradeManager: Intraday Trades Directory %s does not exist. Hence going to create.", self.intradayTradesDir)
            os.makedirs(self.intradayTradesDir)

        self.order_manager = brokers[get_user_details(short_code).broker]["order_manager"](short_code, broker_handler)

        self.ticker = brokers[get_user_details(short_code).broker]["ticker"](short_code, broker_handler)

        self.ticker.start_ticker(get_user_details(short_code).key, self.access_token)
        self.ticker.register_listener(self.ticker_listener)

        self.ticker.register_symbols(["NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY FIN SERVICE"])

        # Load all trades from json files to app memory
        self.load_trades_from_file()
        self.load_strategies_from_file()

        while len(self.symbol_to_cmp) < 4:
            time.sleep(2)

        self.is_ready = True

        wait_till_market_open("TradeManager")

    async def run(self):  # track and update trades in a loop
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

    def square_off_trade(self, trade, exitReason):
        pass

    def square_off_strategy(self, strategyInstance, exitReason):
        pass

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

    def execute_trade(self, trade: Trade):
        logging.info("TradeManager: Execute trade called for %s", trade)
        trade.initial_stoploss = trade.stopLoss
        # Create order input params object and place order
        oip = OrderInputParams(trade.trading_symbol)
        oip.exchange = trade.exchange
        oip.direction = trade.direction
        oip.product_type = trade.productType
        oip.order_type = OrderType.LIMIT if trade.placeMarketOrder == True else OrderType.SL_LIMIT
        oip.trigger_price = round_to_ticksize(self.short_code, trade.trading_symbol, trade.requestedEntry)
        oip.price = round_to_ticksize(self.short_code, trade.trading_symbol, trade.requestedEntry * (1.01 if trade.direction == Direction.LONG else 0.99))
        oip.qty = trade.qty
        oip.tag = trade.strategy
        if trade.is_futures == True or trade.isOptions == True:
            oip.is_fno = True
        try:
            placed_order = self.order_manager.place_order(oip)
            trade.entry_orders.append(placed_order)
            self.orders[placed_order.orderId] = placed_order
        except Exception as e:
            logging.error("TradeManager: Execute trade failed for tradeID %s: Error => %s", trade.tradeID, str(e))
            return False

        logging.info("TradeManager: Execute trade successful for %s and entryOrder %s", trade, trade.entry_orders)
        return True

    def register_strategy(self, strategy_instance):
        self.strategy_to_instance[strategy_instance.getName()] = strategy_instance
        strategy_instance.strategyData = self.strategies_data.get(strategy_instance.getName(), None)
        strategy_instance.orderQueue = self.order_queue

    def dergister_strategy(self, strategy_name):
        del self.strategy_to_instance[strategy_name]

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

    def convert_json_to_order(self, jsonData):
        if jsonData == None:
            return None
        order = Order()
        order.trading_symbol = jsonData["trading_symbol"]
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

    def convert_json_to_trade(self, jsonData):
        trade = Trade(jsonData["trading_symbol"])
        trade.tradeID = jsonData["tradeID"]
        trade.strategy = jsonData["strategy"]
        trade.direction = jsonData["direction"]
        trade.productType = jsonData["productType"]
        trade.is_futures = jsonData["isFutures"]
        trade.isOptions = jsonData["isOptions"]
        trade.optionType = jsonData["optionType"]
        trade.underLying = jsonData.get("underLying", "")
        trade.placeMarketOrder = jsonData["placeMarketOrder"]
        trade.intradaySquareOffTimestamp = jsonData["intradaySquareOffTimestamp"]
        trade.requestedEntry = jsonData["requestedEntry"]
        trade.entry = jsonData["entry"]
        trade.qty = jsonData["qty"]
        trade.filledQty = jsonData["filledQty"]
        trade.initial_stoploss = jsonData["initialStopLoss"]
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
            trade.entry_orders.append(self.convert_json_to_order(entryOrder))
        for slOrder in jsonData["slOrder"]:
            trade.slOrder.append(self.convert_json_to_order(slOrder))
        for trargetOrder in jsonData["targetOrder"]:
            trade.targetOrder.append(self.convert_json_to_order(trargetOrder))

    def ticker_listener(self, tick):
        # logging.info('tickerLister: new tick received for %s = %f', tick.trading_symbol, tick.lastTradedPrice);
        # Store the latest tick in map
        self.symbol_to_cmp[tick.trading_symbol] = tick.lastTradedPrice
        if tick.exchange_timestamp:
            self.symbol_to_cmp["exchange_timestamp"] = tick.exchange_timestamp
        # # On each new tick, get a created trade and call its strategy whether to place trade or not
        # for strategy in self.strategyToInstanceMap:
        #     longTrade = self.getUntriggeredTrade(tick.trading_symbol, strategy, Direction.LONG)
        #     shortTrade = self.getUntriggeredTrade(tick.trading_symbol, strategy, Direction.SHORT)
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
