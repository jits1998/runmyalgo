import logging
import time

from kiteconnect import KiteTicker  # type: ignore[import-untyped]

from broker import BaseTicker
from instruments import get_instrument_data_by_symbol, get_instrument_data_by_token
from models import TickData


class ZerodhaTicker(BaseTicker):
    def __init__(self, short_code, broker_handler):
        super().__init__(short_code, broker_handler)

    def start_ticker(self, appKey, access_token):
        if access_token == None:
            logging.error("ZerodhaTicker startTicker: Cannot start ticker as access_token is empty")
            return

        ticker = KiteTicker(appKey, access_token)
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
        self.on_connect()

    def on_close(self, ws, code, reason):
        self.on_disconnect(code, reason)

    def on_error(self, ws, code, reason):
        self.on_error(code, reason)

    def on_reconnect(self, ws, attemptsCount):
        self.on_reconnect(attemptsCount)

    def on_noreconnect(self, ws):
        self.on_max_reconnect_attempts()

    def on_order_update(self, ws, data):
        self.on_order_update(data)
