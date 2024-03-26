import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from core import Quote

T = TypeVar("T")


class BaseHandler(Generic[T]):

    def __init__(self, broker: T) -> None:
        self.broker: T = broker
        self.instrumentsList: List[Dict[str, str]] = []
        
    @abstractmethod
    def set_access_token(self, accessToken) -> None:
        ...
    
    @abstractmethod
    def margins(self) -> List:
        ...
    
    @abstractmethod
    def positions(self) -> List:
        ...
    
    @abstractmethod
    def orders(self) -> List:
        ...
    
    @abstractmethod
    def quote(self, key: str) -> Dict:
        ...
    
    @abstractmethod
    def instruments(self, exchange: str) -> List:
        ...
    
    def getBrokerHandle(self) -> T:
        return self.broker
    
    @abstractmethod
    def getQuote(self, tradingSymbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        ...
    
    @abstractmethod
    def getIndexQuote(self, tradingSymbol: str, short_code: str, exchange: str = "NSE"):
        ...


class BaseLogin(ABC):

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
        ...

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


class BaseOrderManager(ABC):

    def __init__(self, broker: str, brokerHandle: T):
        self.broker: str = broker
        self.brokerHandle: T = brokerHandle

    @abstractmethod
    def placeOrder(self, orderInputParams) -> bool:
        ...

    @abstractmethod
    def modifyOrder(self, order, orderModifyParams) -> bool:
        ...

    @abstractmethod
    def modifyOrderToMarket(self, order) -> bool:
        ...

    @abstractmethod
    def cancelOrder(self, order) -> bool:
        ...

    @abstractmethod
    def fetchAndUpdateAllOrderDetails(self, orders) -> None:
        ...

    @abstractmethod
    def convertToBrokerProductType(self, productType):
        ...

    @abstractmethod
    def convertToBrokerOrderType(self, orderType):
        ...

    @abstractmethod
    def convertToBrokerDirection(self, direction):
        ...


class BaseTicker(ABC):
    def __init__(self, short_code: str, brokerHandler: BaseHandler) -> None:
        self.short_code: str = short_code
        self.broker: str
        self.brokerHandler: BaseHandler = brokerHandler
        self.ticker = None
        self.tickListeners: List[Callable] = []

    @abstractmethod
    def startTicker(self, appKey, accessToken) -> None:
        ...

    
    def stopTicker(self) -> None:
        ...

    def registerListener(self, listener) -> None:
        # All registered tick listeners will be notified on new ticks
        self.tickListeners.append(listener)

    @abstractmethod
    def registerSymbols(self, symbols: List[str]) -> None:
        ...

    @abstractmethod
    def unregisterSymbols(self, symbols: List[str]) -> None:
        ...

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
        ...
