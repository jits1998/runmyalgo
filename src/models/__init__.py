from enum import Enum

from models.user import UserDetails


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
