from threading import Thread
from time import sleep
from typing import Optional

from broker.base import BaseLogin
from core import TradeManager


class UserDetails(Thread):
    broker: str
    key: str
    secret: str
    short_code: str
    clientID: str
    algoType: str
    multiple: float
    loginHandler: Optional[BaseLogin]
    tradeManager: Optional[TradeManager]

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None) -> None:
        super(UserDetails, self).__init__(group=group, target=target, name=name)
        (self.broker,) = args
        self.loginHandler = None
        self.tradeManager = None

    def run(self) -> None:
        while True:
            sleep(10)

    def getName(self) -> str:
        return self.short_code
