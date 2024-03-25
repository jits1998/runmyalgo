from threading import Thread
from time import sleep

from broker.base import BaseLogin
from core import TradeManager


class UserDetails(Thread):
    broker: str
    key: str
    secret: str
    short_code: str
    clientID: str
    loginHandler: BaseLogin
    tradeManager: TradeManager

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None) -> None:
        super(UserDetails, self).__init__(group=group, target=target, name=name)
        (self.broker,) = args

    def run(self) -> None:
        while True:
            sleep(10)

    def getName(self) -> str:
        return self.short_code
