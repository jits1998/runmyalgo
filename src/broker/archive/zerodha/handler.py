import logging
import time

from kiteconnect import KiteConnect  # type: ignore[import-untyped]
from kiteconnect.exceptions import (  # type: ignore[import-untyped]
    DataException,
    NetworkException,
)
from requests.exceptions import ReadTimeout

from broker import BaseHandler
from core import Quote


class ZerodhaHandler(BaseHandler):

    def __init__(self, broker_handle: KiteConnect, config) -> None:
        self.broker_handle: KiteConnect = broker_handle
        self.config = config

    def set_access_token(self, access_token) -> None:
        self.broker_handle.set_access_token(access_token)

    def margins(self) -> list:
        return self.broker_handle.margins()

    def positions(self) -> list:
        return self.broker_handle.positions()

    def orders(self) -> list:
        return self.broker_handle.orders()

    def instruments(self, exchange) -> list:
        return self.broker_handle.instruments(exchange)

    def getBrokerHandle(self) -> KiteConnect:
        return self.broker_handle

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        key = (exchange + ":" + trading_symbol.upper()) if isFnO == True else ("NSE:" + trading_symbol.upper())
        quote = Quote(trading_symbol)

        bQuoteResp = self._get_quote(key)

        bQuote = bQuoteResp[key]

        # convert broker quote to our system quote
        quote.trading_symbol = trading_symbol
        quote.lastTradedPrice = bQuote["last_price"]
        quote.lastTradedQuantity = bQuote["last_quantity"]
        quote.avgTradedPrice = bQuote["average_price"]
        quote.volume = bQuote["volume"]
        quote.totalBuyQuantity = bQuote["buy_quantity"]
        quote.totalSellQuantity = bQuote["sell_quantity"]
        ohlc = bQuote["ohlc"]
        quote.open = ohlc["open"]
        quote.high = ohlc["high"]
        quote.low = ohlc["low"]
        quote.close = ohlc["close"]
        quote.change = bQuote["net_change"]
        quote.oiDayHigh = bQuote["oi_day_high"]
        quote.oiDayLow = bQuote["oi_day_low"]
        quote.oi = bQuote["oi"]
        quote.lowerCiruitLimit = bQuote["lower_circuit_limit"]
        quote.upperCircuitLimit = bQuote["upper_circuit_limit"]

        return quote

    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE") -> Quote:
        key = exchange + ":" + trading_symbol.upper()

        bQuoteResp = self._get_quote(key)

        bQuote = bQuoteResp[key]
        # convert broker quote to our system quote
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.lastTradedPrice = bQuote["last_price"]
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
