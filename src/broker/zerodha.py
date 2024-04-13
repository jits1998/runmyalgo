import logging
import time
from typing import Dict, List

from kiteconnect import KiteConnect, KiteTicker  # type: ignore[import-untyped]

from broker import brokers, tickers
from broker.base import Broker as Base
from broker.base import Ticker as BaseTicker
from config import get_system_config
from core import Quote
from instruments import get_instrument_data_by_symbol, get_instrument_data_by_token
from models import TickData
from models.order import Order, OrderInputParams, OrderModifyParams


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

    def place_order(self, order_input_params: OrderInputParams) -> bool:
        return False

    def modify_order(self, order: Order, order_modify_params: OrderModifyParams) -> bool:
        return False

    def cancel_order(self, order: Order) -> bool:
        return False

    def fetch_update_all_orders(self, orders: List[Order]) -> None: ...

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        return Quote(trading_symbol)

    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE") -> Quote:
        return Quote(trading_symbol)

    def margins(self) -> List:
        return []

    def positions(self) -> List:
        return []

    def orders(self) -> List:
        return []

    def quote(self, key: str) -> Dict:
        return {}

    def instruments(self, exchange) -> list:
        return self.broker_handle.instruments(exchange)


class Ticker(BaseTicker[Broker]):

    def __init__(self, short_code, broker):
        super().__init__(short_code, broker)

    def start_ticker(
        self,
    ):
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
        self.onOrderUpdate(data)


brokers["zerodha"] = Broker
tickers["zerodha"] = Ticker
