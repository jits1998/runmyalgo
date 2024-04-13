import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, Generic, List, Optional, TypeVar

from core import Quote
from models.order import Order, OrderInputParams, OrderModifyParams

T = TypeVar("T")


class Broker(ABC, Generic[T]):
    broker_handle: T
    user_details: Dict[str, str]
    access_token: Optional[str]

    def __init__(self, user_details: Dict[str, str]) -> None:
        self.user_details = user_details
        self.broker_name: str = user_details["broker_name"]
        self.access_token = None
        self.instruments_list: List[Dict[str, str]] = []

    @abstractmethod
    def login(self, args: Dict) -> str: ...

    @abstractmethod
    def place_order(self, order_input_params: OrderInputParams) -> bool: ...

    @abstractmethod
    def modify_order(self, order: Order, order_modify_params: OrderModifyParams) -> bool: ...

    @abstractmethod
    def cancel_order(self, order: Order) -> bool: ...

    @abstractmethod
    def fetch_update_all_orders(self, orders: List[Order]) -> None: ...

    @abstractmethod
    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote: ...

    @abstractmethod
    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE") -> Quote: ...

    @abstractmethod
    def margins(self) -> List: ...

    @abstractmethod
    def positions(self) -> List: ...

    @abstractmethod
    def orders(self) -> List: ...

    @abstractmethod
    def quote(self, key: str) -> Dict: ...

    @abstractmethod
    def instruments(self, exchange: str) -> List: ...

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token

    def get_user_details(self) -> Dict[str, str]:
        return self.user_details

    def get_access_token(self) -> Optional[str]:
        return self.access_token


B = TypeVar("B", bound=Broker, covariant=True)


class Ticker(ABC, Generic[B]):
    def __init__(self, short_code: str, broker: B) -> None:
        self.short_code: str = short_code
        self.broker_name: str
        self.broker = broker
        self.ticker = None
        self.tickListeners: List[Callable] = []

    @abstractmethod
    def start_ticker(sellf) -> None: ...

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