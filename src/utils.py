import threading
from typing import Union

from broker import BaseLogin
from config import getUserConfig
from core import TradeManager
from models import UserDetails


def getUserDetails(short_code: str) -> UserDetails:
    userDetails = None
    for t in threading.enumerate():
        if t.getName() == short_code:
            userDetails: UserDetails = t  # type: ignore

    if userDetails is None:
        userConfig: dict = getUserConfig(short_code)

        userDetails = UserDetails(name=short_code, args=(userConfig["broker"],))
        userDetails.short_code = short_code
        userDetails.clientID = userConfig["clientID"]
        userDetails.secret = userConfig["appSecret"]
        userDetails.key = userConfig["appKey"]
        userDetails.multiple = userConfig["multiple"]
        userDetails.algoType = userConfig["algoType"]

    return userDetails


def getTradeManager(short_code: str) -> Union[TradeManager, None]:
    for t in threading.enumerate():
        if t.getName() == short_code:
            user: UserDetails = t  # type: ignore
            return user.tradeManager
    return None


def getBrokerLogin(short_code: str) -> Union[BaseLogin, None]:
    for t in threading.enumerate():
        if t.getName() == short_code:
            user: UserDetails = t  # type: ignore
            return user.loginHandler
    return None
