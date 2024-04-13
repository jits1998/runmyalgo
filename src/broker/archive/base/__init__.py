import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from core import Quote

T = TypeVar("T")


class BaseHandler(Generic[T]):

    def __init__(self, broker: T) -> None:
        self.broker: T = broker
        self.instruments_list: List[Dict[str, str]] = []

    @abstractmethod
    def set_access_token(self, access_token) -> None: ...

    @abstractmethod
    def margins(self) -> List: ...

    @abstractmethod
    def positions(self) -> List: ...

    @abstractmethod
    def orders(self) -> List: ...

    @abstractmethod
    def instruments(self, exchange: str) -> List: ...

    def getBrokerHandle(self) -> T:
        return self.broker

    @abstractmethod
    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote: ...

    @abstractmethod
    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE"): ...


class BaseLogin(ABC):

    access_token: Optional[str]
    broker_handle: Optional[BaseHandler]

    def __init__(self, user_details: Dict[str, str]) -> None:
        self.user_details = user_details
        self.broker: str = user_details["broker"]
        self.access_token = None
        self.broker_handle = None

    # Derived class should implement login function and return redirect url
    @abstractmethod
    def login(self, args: Dict) -> str: ...

    def set_broker_handle(self, broker_handle: BaseHandler) -> None:
        self.broker_handle = broker_handle

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token
        assert self.broker_handle is not None
        self.broker_handle.set_access_token(access_token)

    def get_user_details(self) -> Dict[str, str]:
        return self.user_details

    def get_access_token(self) -> Optional[str]:
        return self.access_token

    def get_broker_handle(self) -> Optional[BaseHandler]:
        return self.broker_handle


class BaseOrderManager(ABC):

    def __init__(self, broker: str, broker_handle: T):
        self.broker: str = broker
        self.broker_handle: T = broker_handle

    @abstractmethod
    def place_order(self, orderInputParams) -> bool: ...

    @abstractmethod
    def modify_order(self, order, orderModifyParams) -> bool: ...

    @abstractmethod
    def cancel_order(self, order) -> bool: ...

    @abstractmethod
    def fetch_update_all_orders(self, orders) -> None: ...


class BaseTicker(ABC):
    def __init__(self, short_code: str, broker_handle: BaseHandler) -> None:
        self.short_code: str = short_code
        self.broker: str
        self.broker_handle: BaseHandler = broker_handle
        self.ticker = None
        self.tickListeners: List[Callable] = []

    @abstractmethod
    def start_ticker(self, appKey, access_token) -> None: ...

    def stop_ticker(self) -> None: ...

    def register_listener(self, listener) -> None:
        # All registered tick listeners will be notified on new ticks
        self.tickListeners.append(listener)

    @abstractmethod
    def register_symbols(self, symbols: List[str]) -> None: ...

    @abstractmethod
    def unregister_symbols(self, symbols: List[str]) -> None: ...

    def on_new_ticks(self, ticks) -> None:
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
