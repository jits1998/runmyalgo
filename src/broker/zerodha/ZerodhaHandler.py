from typing import Dict

from kiteconnect import KiteConnect  # type: ignore[import-untyped]

from broker import BaseHandler


class ZerodhaHandler(KiteConnect, BaseHandler):

    def __init__(self, broker: KiteConnect, config) -> None:
        self.broker: KiteConnect = broker
        self.config = config

    def set_access_token(self, accessToken) -> None:
        self.broker.set_access_token(accessToken)

    def margins(self) -> list:
        return self.broker.margins()

    def positions(self) -> list:
        return self.broker.positions()

    def orders(self) -> list:
        return self.broker.orders()

    def quote(self, key) -> Dict:
        return self.broker.quote(key)

    def instruments(self, exchange) -> list:
        return self.broker.instruments(exchange)

    def getBrokerHandle(self) -> KiteConnect:
        return self.broker
