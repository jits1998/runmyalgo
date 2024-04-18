import csv
import datetime
import logging
import time
import urllib
from io import BytesIO, TextIOWrapper
from typing import Any, Dict, List
from urllib.request import urlopen, urlretrieve
from zipfile import ZipFile

import dateutil.parser
import requests
import socketio  # type: ignore[import-untyped]
from breeze_connect import BreezeConnect  # type: ignore[import-untyped]
from breeze_connect import config as breeze_config

from broker import brokers, tickers
from broker.base import Broker as Base
from broker.base import Ticker as BaseTicker
from config import get_system_config
from core import Quote
from instruments import get_instrument_data_by_symbol, get_instrument_data_by_token
from models import Direction, OrderStatus, OrderType, TickData
from models.order import Order, OrderInputParams, OrderModifyParams
from utils import get_epoch


class Broker(Base[BreezeConnect]):

    def login(self, args: Dict) -> str:
        logging.info("==> ICICILogin .args => %s", args)
        self.system_config = get_system_config()
        self.broker_handle = BreezeConnect(api_key=self.user_details["key"])
        redirect_url = None
        if "apisession" in args:

            apisession = args["apisession"]

            logging.info("ICICI apisession = %s", apisession)

            self.set_access_token(apisession)

            if not self.broker_handle.user_id == self.user_details["client_id"]:
                raise Exception("Invalid User Credentials")

            logging.info("ICICI Login successful. apisession = %s", apisession)

            homeUrl = self.system_config["homeUrl"]
            logging.info("ICICI Redirecting to home page %s", homeUrl)

            redirect_url = homeUrl
        else:
            redirect_url = "https://api.icicidirect.com/apiuser/login?api_key=" + urllib.parse.quote_plus(self.user_details["key"])

        return redirect_url

    def place_order(self, oip: OrderInputParams) -> Order:
        logging.debug("%s:%s:: Going to place order with params %s", self.broker_name, self.short_code, oip)
        breeze = self.broker_handle
        oip.qty = int(oip.qty)
        import math

        freeze_limit = 900 if oip.trading_symbol.startswith("BANK") else 1800
        isd = get_instrument_data_by_symbol(self.short_code, oip.trading_symbol)
        lot_size = isd["lot_size"]
        # leg_count = max(math.ceil(orderInputParams.qty/freeze_limit), 2)
        # slice = orderInputParams.qty / leg_count
        # iceberg_quantity = math.ceil(slice / lot_size) * lot_size
        # iceberg_legs = leg_count

        if oip.qty > freeze_limit and oip.order_type == OrderType.MARKET:
            oip.order_type = OrderType.LIMIT

        try:
            order_info = breeze.place_order(
                stock_code=isd["name"],
                # variety= breeze.VARIETY_REGULAR if orderInputParams.qty<=freeze_limit else breeze.VARIETY_ICEBERG,
                # iceberg_quantity = iceberg_quantity,
                # tradingsymbol=orderInputParams.trading_symbol,
                exchange_code=oip.exchange if oip.is_fno == True else breeze.EXCHANGE_NSE,
                product=self._convert_to_broker_product(oip.trading_symbol),
                action=self._convert_to_broker_direction(oip.direction),
                order_type=self._covert_to_broker_order(oip.order_type),
                quantity=oip.qty,
                price=oip.price if oip.order_type != OrderType.MARKET else "",
                validity="day",
                stoploss=oip.trigger_price if oip.order_type == OrderType.SL_LIMIT else "",
                user_remark=oip.tag[:20],
                right=self._get_instrument_right(oip.trading_symbol),
                strike_price=isd["strike"],
                expiry_date=isd["expiry"],
            )

            order = Order(oip)
            order.order_id = order_info["Success"]["order_id"]
            order.place_timestamp = get_epoch()
            order.update_timestamp = get_epoch()
            self.orders_queue.put_nowait(order)
            logging.info("%s:%s:: Order placed successfully, orderId = %s with tag: %s", self.broker_name, self.short_code, order.order_id, oip.tag)
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order placement in 1 s for %s", self.broker_name, self.short_code, order.order_id)
                import time

                time.sleep(1)
                self.place_order(oip)
            logging.info("%s:%s Order placement failed: %s", self.broker_name, self.short_code, str(order_info))
            if "price cannot be" in order_info["Error"]:
                oip.order_type = OrderType.LIMIT
                return self.place_order(oip)
            else:
                if order_info["Success"] is None:
                    raise (Exception(order_info["Error"]))
                raise Exception(str(e))

    def modify_order(self, order: Order, omp: OrderModifyParams, tradeQty: int) -> Order:
        logging.info("%s:%s:: Going to modify order with params %s", self.broker_name, self.short_code, omp)

        if order.order_type == OrderType.SL_LIMIT and omp.newTriggerPrice == order.trigger_price:
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker_name, self.short_code, omp)
            # nothing to modify
            return order
        elif order.order_type == OrderType.LIMIT and omp.newPrice < 0 or omp.newPrice == order.price:
            # nothing to modify
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker_name, self.short_code, omp)
            return order

        breeze = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800

        try:
            orderId = breeze.modify_order(
                order_id=order.order_id,
                exchange_code="NFO",
                quantity=int(omp.newQty) if omp.newQty > 0 else None,
                price=omp.newPrice if omp.newPrice > 0 else None,
                stoploss=omp.newTriggerPrice if omp.newTriggerPrice > 0 and order.order_type == OrderType.SL_LIMIT else None,
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

    def cancel_order(self, order: Order) -> Order:
        logging.debug("%s:%s Going to cancel order %s", self.broker_name, self.short_code, order.order_id)
        breeze = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800
        try:
            orderId = breeze.cancel_order(order_id=order.order_id, exchange_code="NFO")

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

    def fetch_update_all_orders(self, orders: Dict[Order, Any]) -> List[Order]:
        logging.debug("%s:%s Going to fetch order book", self.broker_name, self.short_code)
        breeze = self.broker_handle
        orderBook = None
        try:
            orderBook = breeze.get_order_list()
        except Exception as e:
            import traceback

            traceback.format_exc()
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
                assert foundOrder is not None
                logging.debug("Found order for orderId %s", foundOrder.order_id)
                foundOrder.qty = int(bOrder["quantity"])
                foundOrder.pending_qty = int(bOrder["pending_quantity"])
                foundOrder.filled_qty = foundOrder.qty - foundOrder.pending_qty

                foundOrder.order_status = bOrder["status"]
                if foundOrder.order_status == OrderStatus.CANCELLED and foundOrder.filled_qty > 0:
                    # Consider this case as completed in our system as we cancel the order with pending qty when strategy stop timestamp reaches
                    foundOrder.order_status = OrderStatus.COMPLETE
                foundOrder.price = float(bOrder["price"])
                foundOrder.trigger_price = float(bOrder["SLTP_price"]) if bOrder["SLTP_price"] != None else 0.0
                foundOrder.average_price = float(bOrder["average_price"])
                foundOrder.update_timestamp = bOrder["exchange_acknowledgement_date"]
                logging.debug("%s:%s:%s Updated order %s", self.broker_name, self.short_code, orders[foundOrder], foundOrder)
                numOrdersUpdated += 1
            elif foundChildOrder != None:
                assert parentOrder is not None
                oip = OrderInputParams(parentOrder.trading_symbol)
                oip.exchange = parentOrder.exchange
                oip.product_type = parentOrder.product_type
                oip.order_type = parentOrder.order_type
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

    def handle_order_update_tick(self, order: Order, tick: Dict):
        order.order_status = tick["orderStatus"]
        order.average_price = float(tick.get("averageExecutredRate", 0.0))
        order.filled_qty = int(tick["executedQuantity"])
        order.update_timestamp = int(datetime.datetime.strptime(tick["messageDate"] + " " + tick["messageTime"], "%d-%m-%Y %H:%M:%S").timestamp())

    def _get_instrument_right(self, trading_symbol):
        if trading_symbol[-2:] == "PE":
            return "Put"
        elif trading_symbol[-2:] == "CE":
            return "Call"
        return "Others"

    def _convert_to_broker_product(self, trading_symbol):
        if trading_symbol[-2:] == "PE" or trading_symbol[-2:] == "CE":
            return "options"
        elif "FUT" in trading_symbol:
            return "futures"
        return "cash"

    def _covert_to_broker_order(self, order_type):
        breeze = self.broker_handle
        if order_type == OrderType.LIMIT:
            return "limit"
        elif order_type == OrderType.MARKET:
            return "market"
        elif order_type == OrderType.SL_LIMIT:
            return "stoploss"
        return None

    def _convert_to_broker_direction(self, direction):
        if direction == Direction.LONG:
            return "buy"
        elif direction == Direction.SHORT:
            return "sell"
        return None

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        isd = get_instrument_data_by_symbol(short_code, trading_symbol)
        bQuote = self._quote(isd)
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.last_traded_price = bQuote["ltp"]
        quote.last_traded_quantity = 0
        quote.avg_traded_price = 0
        quote.volume = bQuote["total_quantity_traded"]
        quote.total_buy_quantity = 0
        quote.total_sell_quantity = 0
        quote.open = bQuote["open"]
        quote.high = bQuote["high"]
        quote.low = bQuote["low"]
        quote.close = bQuote["previous_close"]
        quote.change = 0
        quote.oi_day_high = 0
        quote.oi_day_low = 0
        quote.oi = 0
        quote.lower_ciruit_limit = bQuote["lower_circuit"]
        quote.upper_circuit_limit = bQuote["upper_circuit"]

        return quote

    def get_index_quote(self, trading_symbol, short_code, exchange="NSE"):
        isd = get_instrument_data_by_symbol(short_code, trading_symbol)
        bQuote = self._quote(isd)
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.last_traded_price = bQuote["ltp"]
        quote.last_traded_quantity = 0
        quote.avg_traded_price = 0
        quote.volume = bQuote["total_quantity_traded"]
        quote.total_buy_quantity = 0
        quote.total_sell_quantity = 0
        quote.open = bQuote["open"]
        quote.high = bQuote["high"]
        quote.low = bQuote["low"]
        quote.close = bQuote["previous_close"]
        quote.change = 0
        quote.oi_day_high = 0
        quote.oi_day_low = 0
        quote.oi = 0
        quote.lower_ciruit_limit = bQuote["lower_circuit"]
        quote.upper_circuit_limit = bQuote["upper_circuit"]

        return quote

    def _quote(self, isd):
        product_type = ""
        right = ""
        retry = False
        if isd["instrument_type"] == "PE":
            product_type = "options"
            right = "PUT"
        elif isd["instrument_type"] == "CE":
            product_type = "options"
            right = "CALL"
        elif isd["expiry"] != "":
            product_type = "futures"
            right = "Others"

        try:
            return self.broker_handle.get_quotes(
                stock_code=isd["name"],
                exchange_code=isd["exchange"],
                expiry_date=isd["expiry"],
                product_type=product_type,
                right=right,
                strike_price=isd["strike"],
            )["Success"][0]
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                retry = True
        if retry:
            time.sleep(1)
            logging.info("retrying get_quote after 1 s for %s", isd["name"])
            return self._quote(isd)

    def margins(self) -> List:
        return []

    def positions(self) -> List:
        return []

    def orders(self) -> List:
        order_list = self.broker_handle.get_order_list(
            exchange_code="NFO",
            from_date=datetime.datetime.now().isoformat()[:10] + "T05:30:00.000Z",
            to_date=datetime.datetime.now().isoformat()[:10] + "T05:30:00.000Z",
        )["Success"]

        if order_list == None:
            return []
        else:
            for order in order_list:
                if order["status"] == "Executed":
                    order["status"] = OrderStatus.COMPLETE
                order["tradingsymbol"] = [
                    x
                    for x in self.instruments_list
                    if x["name"] == order["stock_code"]
                    and x["strike"] == str(order["strike_price"]).split(".")[0]
                    and x["expiry"] == order["expiry_date"]
                    and x["instrument_type"] == ("PE" if order["right"] == "Put" else "CE")
                ][0]["tradingsymbol"]
                order["tag"] = order["user_remark"]
                order["transaction_type"] = order["action"]
        return order_list

    def instruments(self, exchange: str) -> List:
        # get instruments file to get tradesymbols
        trading_symbolDict = {}
        f, _ = urlretrieve("https://api.kite.trade/instruments")
        with open(f, newline="") as csvfile:
            r = csv.DictReader(csvfile)
            for row in r:
                trading_symbolDict[row["exchange_token"]] = row["tradingsymbol"]

        resp = urlopen(breeze_config.SECURITY_MASTER_URL)
        zipfile = ZipFile(BytesIO(resp.read()))
        mapper_exchangecode_to_file = breeze_config.ISEC_NSE_CODE_MAP_FILE

        if exchange == "NFO":
            exchange = "fonse"

        file_key = mapper_exchangecode_to_file.get(exchange.lower())

        records: List = []

        if file_key is None:
            return records

        with zipfile.open(file_key) as required_file:

            # field_names={'nse':['Token', 'ShortName', 'Series', 'CompanyName', 'ticksize', 'Lotsize',
            #              'DateOfListing', 'DateOfDeListing', 'IssuePrice', 'FaceValue', 'ISINCode',
            #              '52WeeksHigh', '52WeeksLow', 'LifeTimeHigh', 'LifeTimeLow', 'HighDate',
            #              'LowDate', 'Symbol', 'InstrumentType', 'PermittedToTrade', 'IssueCapital',
            #              'WarningPercent', 'FreezePercent', 'CreditRating', 'IssueRate', 'IssueStartDate',
            #             'InterestPaymentDate', 'IssueMaturityDate', 'BoardLotQty', 'Name', 'ListingDate',
            #             'ExpulsionDate', 'ReAdmissionDate', 'RecordDate', 'ExpiryDate', 'NoDeliveryStartDate',
            #             'NoDeliveryEndDate', 'MFill', 'AON', 'ParticipantInMarketIndex', 'BookClsStartDate',
            #             'NoDeliveryEndDate', 'MFill', 'AON', 'ParticipantInMarketIndex', 'BookClsStartDate',
            #             'BookClsEndDate', 'EGM', 'AGM', 'Interest', 'Bonus', 'Rights', 'Dividends',
            #             'LocalUpdateDateTime', 'DeleteFlag', 'Remarks', 'NormalMarketStatus', 'OddLotMarketStatus',
            #             'SpotMarketStatus', 'AuctionMarketStatus', 'NormalMarketEligibility', 'OddLotlMarketEligibility',
            #             'SpotMarketEligibility', 'AuctionlMarketEligibility', 'MarginPercentage', 'ExchangeCode'],
            #             'bse':None,
            #             'fonse': None}
            reader = csv.DictReader(TextIOWrapper(required_file, "utf-8"))

            for row in reader:
                instrument = {}
                if reader.line_num == 1:
                    continue

                if exchange.lower() == "nse" and row[' "Series"'] in ["EQ", "0"]:
                    instrument["exchange_token"] = row["Token"]
                    instrument["tradingsymbol"] = row[' "ExchangeCode"'] if row[' "Series"'] not in ["0"] else row["Token"]
                    instrument["instrument_token"] = row["Token"]
                    instrument["name"] = row[' "ShortName"']
                    instrument["last_price"] = 0.0
                    instrument["expiry"] = row[' "ExpiryDate"']
                    instrument["strike"] = 0
                    instrument["tick_size"] = float(row[' "ticksize"']) / 100
                    instrument["lot_size"] = int(row[' "Lotsize"'])
                    instrument["instrument_type"] = "EQ"
                    instrument["segment"] = "NSE" if row[' "Series"'] not in ["0"] else "INDICES"
                    instrument["exchange"] = "NSE"
                    records.append(instrument)
                elif exchange.lower() == "fonse":
                    # row["last_price"] = float(row["last_price"])
                    # row["strike"] = float(row["strike"])
                    # row["tick_size"] = float(row["tick_size"])
                    # row["lot_size"] = int(row["lot_size"])

                    instrument["exchange_token"] = row["Token"]
                    instrument["tradingsymbol"] = trading_symbolDict.get(instrument["exchange_token"], None)
                    if instrument["tradingsymbol"] is None:
                        continue
                    instrument["instrument_token"] = row["Token"]
                    instrument["name"] = row["ShortName"]
                    instrument["last_price"] = 0.0
                    instrument["expiry"] = row["ExpiryDate"]
                    instrument["strike"] = row["StrikePrice"]
                    instrument["tick_size"] = float(row["TickSize"]) / 100.0
                    instrument["lot_size"] = int(row["LotSize"])
                    instrument["instrument_type"] = row["OptionType"] if row["OptionType"] != "XX" else "FUT"
                    instrument["segment"] = "NFO-" + row["Series"][:3]
                    instrument["exchange"] = "NFO"
                    # Parse date
                    if len(instrument["expiry"]) == 10:
                        instrument["expiry"] = dateutil.parser.parse(instrument["expiry"]).date()
                    records.append(instrument)
                else:
                    pass

        return records

    def set_access_token(self, access_token) -> None:
        try:
            super().set_access_token(access_token)
            self.broker_handle.generate_session(session_token=access_token, api_secret=self.user_details["secret"])
        except Exception as e:
            raise Exception("can't generate session as {}, clear web session".format(str(e)))


class Ticker(BaseTicker[Broker]):

    def __init__(self, short_code, broker_handler: Broker):
        super().__init__(short_code, broker_handler)

    def start_ticker(self):

        ticker = self.broker.broker_handle

        logging.info("ICICI Ticker: Going to connect..")
        self.ticker = ticker
        try:
            connected = False
            while connected == False:
                try:
                    self.ticker.ws_connect()
                    connected = True
                except Exception as e:
                    time.sleep(1)
                    # retry

            connected = False
            while connected == False:
                try:
                    self.ticker.subscribe_feeds(get_order_notification=True)
                    connected = True
                except Exception as e:
                    time.sleep(1)
                    # retry

            def on_ticks(bTick):
                if "symbol" in bTick:
                    logging.debug(bTick["symbol"] + " => " + str(bTick["last"]))
                    # convert broker specific Ticks to our system specific Ticks (models.TickData) and pass to super class function
                    ticks = []
                    isd = get_instrument_data_by_token(self.short_code, bTick["symbol"][4:])
                    trading_symbol = isd["tradingsymbol"]
                    tick = TickData(trading_symbol)
                    tick.lastTradedPrice = bTick["last"]
                    if not isd["segment"] == "INDICES":
                        tick.lastTradedQuantity = bTick["ltq"]
                        tick.avgTradedPrice = bTick["avgPrice"]
                        tick.volume = bTick["ttq"]
                        tick.totalBuyQuantity = bTick["totalBuyQt"]
                        tick.totalSellQuantity = bTick["totalSellQ"]
                    # else:
                    #   tick.exchange_timestamp = bTick['exchange_timestamp']
                    tick.open = bTick["open"]
                    tick.high = bTick["high"]
                    tick.low = bTick["low"]
                    tick.close = bTick["close"]
                    tick.change = bTick["change"]
                    ticks.append(tick)
                    self.on_new_ticks(ticks)
                else:
                    self.on_order_update(bTick)

            # ticker.subscribe_feeds(get_order_notification=True)
            self.ticker.on_ticks = on_ticks
        except socketio.exceptions.ConnectionError as e:
            if str(e) == "Already connected":
                return
            else:
                raise e

    def stop_ticker(self):
        logging.info("ICICITicker: stopping..")
        self.ticker.close(1000, "Manual close")

    def register_symbols(self, symbols, mode=None):
        # breeze.subscribe_feeds(stock_token="1.1!500780")
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker registerSymbol: %s token = %s", symbol, token)
            print(self.ticker.subscribe_feeds(stock_token="4.1!" + token))
            tokens.append(token)

        logging.debug("ICICITicker Subscribing tokens %s", tokens)

    def unregister_symbols(self, symbols):
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker unregisterSymbols: %s token = %s", symbol, token)
            tokens.append(token)

        logging.info("ICICITicker Unsubscribing tokens %s", tokens)
        self.ticker.unsubscribe(tokens)


brokers["icici"] = Broker
tickers["icici"] = Ticker
