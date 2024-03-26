from typing import Dict

from kiteconnect import KiteConnect  # type: ignore[import-untyped]

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
        raise Exception("Method not to be called")
