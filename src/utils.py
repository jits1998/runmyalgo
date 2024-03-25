import threading

from core import TradeManager
from models import UserDetails


def getTradeManager(short_code: str) -> TradeManager:
    for t in threading.enumerate():
        if t.getName() == short_code:
            user: UserDetails = t  # type: ignore
            return user.tradeManager
    return None  # type: ignore
