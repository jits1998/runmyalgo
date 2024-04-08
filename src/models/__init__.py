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


class OrderAs(Enum):
    ENTRY = "ENTRY"
    SL = "SL"
    TARGET = "TARGET"


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


class TradeExitReason(Enum):
    SL_HIT = "SL HIT"
    TRAIL_SL_HIT = "TRAIL SL HIT"
    TARGET_HIT = "TARGET HIT"
    SQUARE_OFF = "SQUARE OFF"
    SL_CANCELLED = "SL CANCELLED"
    TARGET_CANCELLED = "TARGET CANCELLED"
    STRATEGY_SL_HIT = "STGY SL HIT"
    STRATEGY_TRAIL_SL_HIT = "STGY TRAIL SL HIT"
    STRATEGY_TARGET_HIT = "STGY TARGET HIT"
    TRADE_FAILED = "TRADE FAILED"
    MANUAL_EXIT = "MANUAL EXIT"


class TradeState(Enum):
    CREATED = "created"  # Trade created but not yet order placed, might have not triggered
    ACTIVE = "active"  # order placed and trade is active
    COMPLETED = "completed"  # completed when exits due to SL/Target/SquareOff
    CANCELLED = "cancelled"  # cancelled/rejected comes under this state only
    DISABLED = "disabled"  # disable trade if not triggered within the time limits or for any other reason
