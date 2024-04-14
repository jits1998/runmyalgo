import logging
import uuid
from datetime import datetime
from typing import List, Optional

from models import Direction, ProductType, TradeState
from models.order import Order


class Trade:

    def __init__(self, trading_symbol=None, strategy="") -> None:
        self.exchange = "NSE"
        self.trade_id = ((strategy + ":") if not strategy == "" else "") + str(uuid.uuid4())  # Unique ID for each trade
        self.trading_symbol = trading_symbol
        self.strategy = strategy
        self.direction = Direction.LONG
        self.product_type = ProductType.MIS
        self.is_futures = False  # Futures trade
        self.is_options = False  # Options trade
        self.optionType = None  # CE/PE. Applicable only if isOptions is True
        self.underLying = None  # NIFTY BANK / NIFTY 50, only if isOptions or isFutures set to True
        self.place_market_order = False  # True means place the entry order with Market Order Type
        self.intraday_squareoff_timestamp = None  # Can be strategy specific. Some can square off at 15:00:00 some can at 15:15:00 etc.
        self.requested_entry = 0.0  # Requested entry
        self.entry = 0.0  # Actual entry. This will be different from requestedEntry if the order placed is Market order
        self.qty = 0  # Requested quantity
        self.filled_qty = 0  # In case partial fill qty is not equal to filled quantity
        self.initial_stoploss = 0.0  # Initial stop loss
        # This is the current stop loss. In case of trailing SL the current stopLoss and initialStopLoss will be different after some time
        self._stopLoss = 0.0
        self.target = 0.0  # Target price if applicable
        self.cmp = 0.0  # Last traded price
        self.stoploss_percentage = 0.0
        self.stoploss_underlying_percentage = 0.0

        self.tradeState = TradeState.CREATED  # state of the trade
        self.timestamp = 0  # Set this timestamp to strategy timestamp if you are not sure what to set
        self.createTimestamp = int(datetime.timestamp(datetime.now()))  # Timestamp when the trade is created (Not triggered)
        self.startTimestamp = 0  # Timestamp when the trade gets triggered and order placed
        self.endTimestamp = 0  # Timestamp when the trade ended
        self.pnl = 0.0  # Profit loss of the trade. If trade is Active this shows the unrealized pnl else realized pnl
        self.pnlPercentage = 0.0  # Profit Loss in percentage terms
        self.exit = 0.0  # Exit price of the trade
        self.exitReason = None  # SL/Target/SquareOff/Any Other

        self.entry_orders: List[Order] = []  # Object of Type ordermgmt.Order
        self.slOrder: List[Order] = []  # Object of Type ordermgmt.Order
        self.targetOrder: List[Order] = []  # Object of Type ordermgmt.Order

    @property
    def stopLoss(self):
        return self._stopLoss

    @stopLoss.setter
    def stopLoss(self, stoploss):
        self._stopLoss = stoploss

    def equals(self, trade):  # compares to trade objects and returns True if equals
        if trade == None:
            return False
        if self.trade_id == trade.tradeID:
            return True
        if self.trading_symbol != trade.trading_symbol:
            return False
        if self.strategy != trade.strategy:
            return False
        if self.direction != trade.direction:
            return False
        if self.product_type != trade.productType:
            return False
        if self.requested_entry != trade.requestedEntry:
            return False
        if self.qty != trade.qty:
            return False
        if self.timestamp != trade.timestamp:
            return False
        if self.stoploss_percentage != trade.stopLossPercentage:
            return False
        if self.stopLoss != trade.stopLoss:
            return False
        if self.target != trade.target:
            return False
        return True

    def __str__(self):
        return (
            "ID="
            + str(self.trade_id)
            + ", state="
            + self.tradeState
            + ", symbol="
            + self.trading_symbol
            + ", strategy="
            + self.strategy
            + ", direction="
            + self.direction
            + ", MarketOrder="
            + str(self.place_market_order)
            + ", productType="
            + self.product_type
            + ", reqEntry="
            + str(self.requested_entry)
            + ", stopLoss="
            + str(self.stopLoss)
            + ", target="
            + str(self.target)
            + ", entry="
            + str(self.entry)
            + ", exit="
            + str(self.exit)
            + ", profitLoss ="
            + str(self.pnl)
        )
