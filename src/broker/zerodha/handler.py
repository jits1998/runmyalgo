import logging
from typing import Dict

from kiteconnect import KiteConnect  # type: ignore[import-untyped]
from kiteconnect.exceptions import (  # type: ignore[import-untyped]
    DataException,
    NetworkException,
)
from requests.exceptions import ReadTimeout

from broker import BaseHandler
from core import Quote


class ZerodhaHandler(BaseHandler):

    def __init__(self, brokerHandle: KiteConnect, config) -> None:
        self.brokerHandle: KiteConnect = brokerHandle
        self.config = config

    def set_access_token(self, accessToken) -> None:
        self.brokerHandle.set_access_token(accessToken)

    def margins(self) -> list:
        return self.brokerHandle.margins()

    def positions(self) -> list:
        return self.brokerHandle.positions()

    def orders(self) -> list:
        return self.brokerHandle.orders()

    def quote(self, key) -> Dict:
        return self.brokerHandle.quote(key)

    def instruments(self, exchange) -> list:
        return self.brokerHandle.instruments(exchange)

    def getBrokerHandle(self) -> KiteConnect:
        return self.brokerHandle

    def getQuote(self, tradingSymbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        key = (exchange +':' + tradingSymbol.upper()) if isFnO == True else ('NSE:' + tradingSymbol.upper())
        quote = Quote(tradingSymbol)

        bQuoteResp = self._getQuote(self.brokerHandle, key)

        bQuote = bQuoteResp[key]
        
        # convert broker quote to our system quote
        quote.tradingSymbol = tradingSymbol
        quote.lastTradedPrice = bQuote['last_price']
        quote.lastTradedQuantity = bQuote['last_quantity']
        quote.avgTradedPrice = bQuote['average_price']
        quote.volume = bQuote['volume']
        quote.totalBuyQuantity = bQuote['buy_quantity']
        quote.totalSellQuantity = bQuote['sell_quantity']
        ohlc = bQuote['ohlc']
        quote.open = ohlc['open']
        quote.high = ohlc['high']
        quote.low = ohlc['low']
        quote.close = ohlc['close']
        quote.change = bQuote['net_change']
        quote.oiDayHigh = bQuote['oi_day_high']
        quote.oiDayLow = bQuote['oi_day_low']
        quote.oi = bQuote['oi']
        quote.lowerCiruitLimit = bQuote['lower_circuit_limit']
        quote.upperCircuitLimit = bQuote['upper_circuit_limit']
        
        return quote
    
    def getIndexQuote(self, tradingSymbol: str, short_code: str, exchange: str = "NSE") -> Quote:
        key = exchange + ':' + tradingSymbol.upper()

        bQuoteResp = self._getQuote(self.brokerHandle, key)

        bQuote = bQuoteResp[key]
        # convert broker quote to our system quote
        quote = Quote(tradingSymbol)
        quote.tradingSymbol = tradingSymbol
        quote.lastTradedPrice = bQuote['last_price']
        ohlc = bQuote['ohlc']
        quote.open = ohlc['open']
        quote.high = ohlc['high']
        quote.low = ohlc['low']
        quote.close = ohlc['close']
        quote.change = bQuote['net_change']
        return quote
        
    def _getQuote(self, brokerHandle, key):
        retry = True
        bQuoteResp = None

        while retry:
            retry = False
            try: 
                bQuoteResp = brokerHandle.quote(key)
            except DataException as de:
                if de.code in [503,502]:
                    retry = True
            except NetworkException as ne:
                if ne.code in [429]:
                    time.sleep(1) #extra 1 sec wait for too many requests
                    retry = True
            except ReadTimeout:
                retry = True
            if retry:
                import time
                time.sleep(1)
                logging.info("retrying getQuote after 1 s for %s", key)
        return bQuoteResp
