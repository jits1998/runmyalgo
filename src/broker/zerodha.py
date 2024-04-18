import logging
import time
from typing import Dict, List

from kiteconnect import KiteConnect, KiteTicker  # type: ignore[import-untyped]
from kiteconnect.exceptions import (  # type: ignore[import-untyped]
    DataException,
    NetworkException,
)
from requests import ReadTimeout  # type: ignore[import-untyped]

from broker import brokers, tickers
from broker.base import Broker as Base
from broker.base import Ticker as BaseTicker
from config import get_system_config
from core import Quote
from instruments import get_instrument_data_by_symbol, get_instrument_data_by_token
from models import Direction, OrderStatus, OrderType, ProductType, TickData
from models.order import Order, OrderInputParams, OrderModifyParams
from utils import get_epoch


class Broker(Base[KiteConnect]):

    def login(self, args: Dict) -> str:
        logging.info("==> ZerodhaLogin .args => %s", args)
        systemConfig = get_system_config()
        self.broker_handle = KiteConnect(api_key=self.user_details["key"])
        redirect_url = None
        if "request_token" in args:
            requestToken = args["request_token"]
            logging.info("Zerodha requestToken = %s", requestToken)
            broker_session = self.broker_handle.generate_session(requestToken, api_secret=self.user_details["secret"])

            if not broker_session["user_id"] == self.user_details["clientID"]:
                raise Exception("Invalid User Credentials")

            access_token = broker_session["access_token"]
            logging.info("Zerodha access_token = %s", access_token)
            # set broker handle and access token to the instance
            self.set_access_token(access_token)

            logging.info("Zerodha Login successful. access_token = %s", access_token)

            # redirect to home page with query param loggedIn=true
            homeUrl = systemConfig["homeUrl"] + "?loggedIn=true"
            logging.info("Zerodha Redirecting to home page %s", homeUrl)
            redirectUrl = homeUrl
        else:
            loginUrl = self.broker_handle.login_url()
            logging.info("Redirecting to zerodha login url = %s", loginUrl)
            redirectUrl = loginUrl

        return redirectUrl

    def place_order(self, oip: OrderInputParams):
        logging.debug("%s:%s:: Going to place order with params %s", self.broker_name, self.short_code, oip)
        kite = self.broker_handle
        oip.qty = int(oip.qty)
        import math

        freeze_limit = 900 if oip.trading_symbol.startswith("BANK") else 1800
        lot_size = get_instrument_data_by_symbol(self.short_code, oip.trading_symbol)["lot_size"]
        leg_count = max(math.ceil(oip.qty / freeze_limit), 2)
        slice = oip.qty / leg_count
        iceberg_quantity = math.ceil(slice / lot_size) * lot_size
        iceberg_legs = leg_count

        if oip.qty > freeze_limit and oip.order_type == OrderType.MARKET:
            oip.order_type = OrderType.LIMIT

        try:
            orderId = kite.place_order(
                variety=kite.VARIETY_REGULAR if oip.qty <= freeze_limit else kite.VARIETY_ICEBERG,
                iceberg_legs=iceberg_legs,
                iceberg_quantity=iceberg_quantity,
                exchange=oip.exchange if oip.is_fno == True else kite.EXCHANGE_NSE,
                tradingsymbol=oip.trading_symbol,
                transaction_type=self.convert_to_broker_direction(oip.direction),
                quantity=oip.qty,
                price=oip.price,
                trigger_price=oip.trigger_price,
                product=self.convert_to_broker_product(oip.product_type),
                order_type=self.covert_to_broker_order(oip.order_type),
                tag=oip.tag[:20],
            )

            logging.info("%s:%s:: Order placed successfully, orderId = %s with tag: %s", self.broker_name, self.short_code, orderId, oip.tag)
            order = Order(oip)
            order.order_id = orderId
            order.place_timestamp = get_epoch()
            order.update_timestamp = get_epoch()
            self.orders_queue.put_nowait(order)
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order placement in 1 s for %s", self.broker_name, self.short_code, order.order_id)
                import time

                time.sleep(1)
                return self.place_order(oip)
            logging.info("%s:%s Order placement failed: %s", self.broker_name, self.short_code, str(e))
            if "Trigger price for stoploss" in str(e):
                oip.order_type = OrderType.LIMIT
                return self.place_order(oip)
            else:
                raise Exception(str(e))

    def modify_order(self, order: Order, omp: OrderModifyParams, tradeQty: int):
        logging.info("%s:%s:: Going to modify order with params %s", self.broker_name, self.short_code, omp)

        if order.order_type == OrderType.SL_LIMIT and omp.newTriggerPrice == order.trigger_price:
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker_name, self.short_code, omp)
            # nothing to modify
            return order
        elif order.order_type == OrderType.LIMIT and omp.newPrice < 0 or omp.newPrice == order.price:
            # nothing to modify
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker_name, self.short_code, omp)
            return order

        kite = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800

        try:
            orderId = kite.modify_order(
                variety=kite.VARIETY_REGULAR if tradeQty <= freeze_limit else kite.VARIETY_ICEBERG,
                order_id=order.order_id,
                quantity=int(omp.newQty) if omp.newQty > 0 else None,
                price=omp.newPrice if omp.newPrice > 0 else None,
                trigger_price=omp.newTriggerPrice if omp.newTriggerPrice > 0 else None,
                order_type=omp.newOrderType if omp.newOrderType != None else None,
            )

            logging.info("%s:%s Order modified successfully for orderId = %s", self.broker_name, self.short_code, orderId)
            order.update_timestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order modification in 1 s for %s", self.broker_name, self.short_code, order.order_id)
                import time

                time.sleep(1)
                self.modify_order(order, omp, tradeQty)
            logging.info("%s:%s Order %s modify failed: %s", self.broker_name, self.short_code, order.order_id, str(e))
            raise Exception(str(e))

    def cancel_order(self, order):
        logging.debug("%s:%s Going to cancel order %s", self.broker_name, self.short_code, order.order_id)
        kite = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800
        try:
            orderId = kite.cancel_order(variety=kite.VARIETY_REGULAR if order.qty <= freeze_limit else kite.VARIETY_ICEBERG, order_id=order.order_id)

            logging.info("%s:%s Order cancelled successfully, orderId = %s", self.broker_name, self.short_code, orderId)
            order.update_timestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order cancellation in 1 s for %s", self.broker_name, self.short_code, order.order_id)
                import time

                time.sleep(1)
                self.cancel_order(order)
            logging.info("%s:%s Order cancel failed: %s", self.broker_name, self.short_code, str(e))
            raise Exception(str(e))

    def fetch_update_all_orders(self, orders):
        logging.debug("%s:%s Going to fetch order book", self.broker_name, self.short_code)
        kite = self.broker_handle
        orderBook = None
        try:
            orderBook = kite.orders()
        except Exception as e:
            logging.error("%s:%s Failed to fetch order book", self.broker_name, self.short_code)
            return []

        logging.debug("%s:%s Order book length = %d", self.broker_name, self.short_code, len(orderBook))
        numOrdersUpdated = 0
        missingOrders = []

        for bOrder in orderBook:
            foundOrder = None
            foundChildOrder = None
            parentOrder = None
            for order in orders.keys():
                if order.order_id == bOrder["order_id"]:
                    foundOrder = order
                if order.order_id == bOrder["parent_order_id"]:
                    foundChildOrder = bOrder
                    parentOrder = order

            if foundOrder != None:
                logging.debug("Found order for orderId %s", foundOrder.order_id)
                foundOrder.qty = bOrder["quantity"]
                foundOrder.filled_qty = bOrder["filled_quantity"]
                foundOrder.pending_qty = bOrder["pending_quantity"]
                foundOrder.order_status = bOrder["status"]
                if foundOrder.order_status == OrderStatus.CANCELLED and foundOrder.filled_qty > 0:
                    # Consider this case as completed in our system as we cancel the order with pending qty when strategy stop timestamp reaches
                    foundOrder.order_status = OrderStatus.COMPLETE
                foundOrder.price = bOrder["price"]
                foundOrder.trigger_price = bOrder["trigger_price"]
                foundOrder.average_price = bOrder["average_price"]
                foundOrder.update_timestamp = bOrder["exchange_update_timestamp"]
                logging.debug("%s:%s:%s Updated order %s", self.broker_name, self.short_code, orders[foundOrder], foundOrder)
                numOrdersUpdated += 1
            elif foundChildOrder != None:
                oip = OrderInputParams(parentOrder.trading_symbol)
                oip.exchange = parentOrder.exchange
                oip.product_type = parentOrder.product_type
                oip.order_type = parentOrder.orderType
                oip.price = parentOrder.price
                oip.trigger_price = parentOrder.trigger_price
                oip.qty = parentOrder.qty
                oip.tag = parentOrder.tag
                oip.product_type = parentOrder.product_type
                order = Order(oip)
                order.order_id = bOrder["order_id"]
                order.parent_order_id = parentOrder.order_id
                order.place_timestamp = get_epoch()  # TODO should get from bOrder
                missingOrders.append(order)

        return missingOrders

    def convert_to_broker_product(self, productType):
        kite = self.broker_handle
        if productType == ProductType.MIS:
            return kite.PRODUCT_MIS
        elif productType == ProductType.NRML:
            return kite.PRODUCT_NRML
        elif productType == ProductType.CNC:
            return kite.PRODUCT_CNC
        return None

    def covert_to_broker_order(self, orderType):
        kite = self.broker_handle
        if orderType == OrderType.LIMIT:
            return kite.ORDER_TYPE_LIMIT
        elif orderType == OrderType.MARKET:
            return kite.ORDER_TYPE_MARKET
        elif orderType == OrderType.SL_MARKET:
            return kite.ORDER_TYPE_SLM
        elif orderType == OrderType.SL_LIMIT:
            return kite.ORDER_TYPE_SL
        return None

    def convert_to_broker_direction(self, direction):
        kite = self.broker_handle
        if direction == Direction.LONG:
            return kite.TRANSACTION_TYPE_BUY
        elif direction == Direction.SHORT:
            return kite.TRANSACTION_TYPE_SELL
        return None

    def handle_order_update_tick(self, order: Order, data: Dict) -> None:
        logging.info(data)

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        key = (exchange + ":" + trading_symbol.upper()) if isFnO == True else ("NSE:" + trading_symbol.upper())
        quote = Quote(trading_symbol)

        bQuoteResp = self._get_quote(key)

        bQuote = bQuoteResp[key]

        # convert broker quote to our system quote
        quote.trading_symbol = trading_symbol
        quote.last_traded_price = bQuote["last_price"]
        quote.last_traded_quantity = bQuote["last_quantity"]
        quote.avg_traded_price = bQuote["average_price"]
        quote.volume = bQuote["volume"]
        quote.total_buy_quantity = bQuote["buy_quantity"]
        quote.total_sell_quantity = bQuote["sell_quantity"]
        ohlc = bQuote["ohlc"]
        quote.open = ohlc["open"]
        quote.high = ohlc["high"]
        quote.low = ohlc["low"]
        quote.close = ohlc["close"]
        quote.change = bQuote["net_change"]
        quote.oi_day_high = bQuote["oi_day_high"]
        quote.oi_day_low = bQuote["oi_day_low"]
        quote.oi = bQuote["oi"]
        quote.lower_ciruit_limit = bQuote["lower_circuit_limit"]
        quote.upper_circuit_limit = bQuote["upper_circuit_limit"]

        return quote

    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE") -> Quote:
        key = exchange + ":" + trading_symbol.upper()

        bQuoteResp = self._get_quote(key)

        bQuote = bQuoteResp[key]
        # convert broker quote to our system quote
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.last_traded_price = bQuote["last_price"]
        ohlc = bQuote["ohlc"]
        quote.open = ohlc["open"]
        quote.high = ohlc["high"]
        quote.low = ohlc["low"]
        quote.close = ohlc["close"]
        quote.change = bQuote["net_change"]
        return quote

    def _get_quote(self, key):
        retry = True
        bQuoteResp = None

        while retry:
            retry = False
            try:
                bQuoteResp = self.broker_handle.quote(key)
            except DataException as de:
                if de.code in [503, 502]:
                    retry = True
            except NetworkException as ne:
                if ne.code in [429]:
                    time.sleep(1)  # extra 1 sec wait for too many requests
                    retry = True
            except ReadTimeout:
                retry = True
            if retry:
                time.sleep(1)
                logging.info("retrying get_quote after 1 s for %s", key)
        return bQuoteResp

    def margins(self) -> List:
        return []

    def positions(self) -> List:
        return []

    def orders(self) -> List:
        return []

    def instruments(self, exchange) -> list:
        return self.broker_handle.instruments(exchange)


class Ticker(BaseTicker[Broker]):

    def __init__(self, short_code, broker):
        super().__init__(short_code, broker)

    def start_ticker(self):
        ticker = KiteTicker(self.broker.broker_handle.api_key, self.broker.access_token)
        ticker.on_connect = self.on_connect
        ticker.on_close = self.on_close
        ticker.on_error = self.on_error
        ticker.on_reconnect = self.on_reconnect
        ticker.on_noreconnect = self.on_noreconnect
        ticker.on_ticks = self.on_ticks
        ticker.on_order_update = self.on_order_update

        logging.info("ZerodhaTicker: Going to connect..")
        self.ticker = ticker
        self.ticker.connect(threaded=True)

        # sleep for 2 seconds for ticker connection establishment
        while self.ticker.ws is None:
            logging.warn("Waiting for ticker connection establishment..")
            time.sleep(2)

    def stop_ticker(self):
        logging.info("ZerodhaTicker: stopping..")
        self.ticker.close(1000, "Manual close")

    def register_symbols(self, symbols, mode=KiteTicker.MODE_FULL):
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ZerodhaTicker registerSymbol: %s token = %s", symbol, token)
            tokens.append(token)

        logging.debug("ZerodhaTicker Subscribing tokens %s", tokens)
        self.ticker.subscribe(tokens)
        self.ticker.set_mode(mode, tokens)

    def unregister_symbols(self, symbols):
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ZerodhaTicker unregisterSymbols: %s token = %s", symbol, token)
            tokens.append(token)

        logging.info("ZerodhaTicker Unsubscribing tokens %s", tokens)
        self.ticker.unsubscribe(tokens)

    def on_ticks(self, ws, brokerTicks):
        # convert broker specific Ticks to our system specific Ticks (models.TickData) and pass to super class function
        ticks = []
        for bTick in brokerTicks:
            isd = get_instrument_data_by_token(self.short_code, bTick["instrument_token"])
            trading_symbol = isd["tradingsymbol"]
            tick = TickData(trading_symbol)
            tick.lastTradedPrice = bTick["last_price"]
            if not isd["segment"] == "INDICES":
                tick.lastTradedQuantity = bTick["last_traded_quantity"]
                tick.avgTradedPrice = bTick["average_traded_price"]
                tick.volume = bTick["volume_traded"]
                tick.totalBuyQuantity = bTick["total_buy_quantity"]
                tick.totalSellQuantity = bTick["total_sell_quantity"]
            else:
                tick.exchange_timestamp = bTick["exchange_timestamp"]
            tick.open = bTick["ohlc"]["open"]
            tick.high = bTick["ohlc"]["high"]
            tick.low = bTick["ohlc"]["low"]
            tick.close = bTick["ohlc"]["close"]
            tick.change = bTick["change"]
            ticks.append(tick)

        self.on_new_ticks(ticks)

    def on_connect(self, ws, response):
        self.onConnect()

    def on_close(self, ws, code, reason):
        self.onDisconnect(code, reason)

    def on_error(self, ws, code, reason):
        self.onError(code, reason)

    def on_reconnect(self, ws, attemptsCount):
        self.onReconnect(attemptsCount)

    def on_noreconnect(self, ws):
        self.onMaxReconnectsAttempt()

    def on_order_update(self, ws, data):
        self.on_order_update(data)


brokers["zerodha"] = Broker
tickers["zerodha"] = Ticker
