import logging
from abc import abstractmethod
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from core import Quote

T = TypeVar("T")


class BaseHandler(Generic[T]):

    def __init__(self, broker: T) -> None:
        self.broker: T = broker
        self.instrumentsList: List[Dict[str, str]] = []

    def set_access_token(self, accessToken) -> None:
        raise Exception("Method not to be called")

    def margins(self) -> List:
        raise Exception("Method not to be called")

    def positions(self) -> List:
        raise Exception("Method not to be called")

    def orders(self) -> List:
        raise Exception("Method not to be called")

    def quote(self, key: str) -> Dict:
        raise Exception("Method not to be called")

    def instruments(self, exchange: str) -> List:
        raise Exception("Method not to be called")

    def getBrokerHandle(self) -> T:
        return self.broker

    def getQuote(self, tradingSymbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        raise Exception("Method not to be called")


class BaseLogin:

    accessToken: Optional[str]
    brokerHandler: Optional[BaseHandler]

    def __init__(self, userDetails: Dict[str, str]) -> None:
        self.userDetails = userDetails
        self.broker: str = userDetails["broker"]
        self.accessToken = None
        self.brokerHandler = None

    # Derived class should implement login function and return redirect url
    @abstractmethod
    def login(self, args: Dict) -> str:
        pass

    def setBrokerHandler(self, brokerHandle: BaseHandler) -> None:
        self.brokerHandler = brokerHandle

    def setAccessToken(self, accessToken: str) -> None:
        self.accessToken = accessToken
        assert self.brokerHandler is not None
        self.brokerHandler.set_access_token(accessToken)

    def getUserDetails(self) -> Dict[str, str]:
        return self.userDetails

    def getAccessToken(self) -> Optional[str]:
        return self.accessToken

    def getBrokerHandler(self) -> Optional[BaseHandler]:
        return self.brokerHandler


class BaseOrderManager:

    def __init__(self, broker: str, brokerHandle: T):
        self.broker: str = broker
        self.brokerHandle: T = brokerHandle

    @abstractmethod
    def placeOrder(self, orderInputParams) -> bool:
        pass

    @abstractmethod
    def modifyOrder(self, order, orderModifyParams) -> bool:
        pass

    @abstractmethod
    def modifyOrderToMarket(self, order) -> bool:
        pass

    @abstractmethod
    def cancelOrder(self, order) -> bool:
        pass

    @abstractmethod
    def fetchAndUpdateAllOrderDetails(self, orders) -> None:
        pass

    @abstractmethod
    def convertToBrokerProductType(self, productType):
        pass

    @abstractmethod
    def convertToBrokerOrderType(self, orderType):
        pass

    @abstractmethod
    def convertToBrokerDirection(self, direction):
        pass


class BaseTicker:
    def __init__(self, short_code: str, brokerHandler: BaseHandler) -> None:
        self.short_code: str = short_code
        self.broker: str
        self.brokerHandler: BaseHandler = brokerHandler
        self.ticker = None
        self.tickListeners: List[Callable] = []

    def startTicker(self, appKey, accessToken) -> None:
        pass

    def stopTicker(self) -> None:
        pass

    def registerListener(self, listener) -> None:
        # All registered tick listeners will be notified on new ticks
        self.tickListeners.append(listener)

    def registerSymbols(self, symbols: List[str]) -> None:
        pass

    def unregisterSymbols(self, symbols: List[str]) -> None:
        pass

    def onNewTicks(self, ticks) -> None:
        # logging.info('New ticks received %s', ticks)
        for tick in ticks:
            for listener in self.tickListeners:
                try:
                    listener(tick)
                except Exception as e:
                    logging.error("BaseTicker: Exception from listener callback function. Error => %s", str(e))

    def onConnect(self) -> None:
        logging.info("Ticker connection successful.")

    def onDisconnect(self, code, reason) -> None:
        logging.error("Ticker got disconnected. code = %d, reason = %s", code, reason)

    def onError(self, code, reason) -> None:
        logging.error("Ticker errored out. code = %d, reason = %s", code, reason)

    def onReconnect(self, attemptsCount) -> None:
        logging.warn("Ticker reconnecting.. attemptsCount = %d", attemptsCount)

    def onMaxReconnectsAttempt(self) -> None:
        logging.error("Ticker max auto reconnects attempted and giving up..")

    def onOrderUpdate(self, data: dict) -> None:
        # logging.info('Ticker: order update %s', data)
        pass
