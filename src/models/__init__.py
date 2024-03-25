from dataclasses import dataclass
from enum import Enum

from models.user import UserDetails


@dataclass
class TickData:
    def __init__(self, tradingSymbol):
        self.tradingSymbol = tradingSymbol
        self.lastTradedPrice = 0
        self.lastTradedQuantity = 0
        self.avgTradedPrice = 0
        self.volume = 0
        self.totalBuyQuantity = 0
        self.totalSellQuantity = 0
        self.open = 0
        self.high = 0
        self.low = 0
        self.close = 0
        self.change = 0
        self.exchange_timestamp = None


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatus(Enum):
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    OPEN_PENDING = "OPEN PENDING"
    VALIDATION_PENDING = "VALIDATION PENDING"
    PUT_ORDER_REQ_RECEIVED = "PUT ORDER REQ RECEIVED"
    TRIGGER_PENDING = "TRIGGER PENDING"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    SL_MARKET = "SL_MARKET"
    SL_LIMIT = "SL_LIMIT"


class ProductType(Enum):
    MIS = "MIS"
    NRML = "NRML"
    CNC = "CNC"


class Segment(Enum):
    EQUITY = "EQUITY"
    FNO = "FNO"
    CURRENCY = "CURRENCY"
    COMMADITY = "COMMADITY"
