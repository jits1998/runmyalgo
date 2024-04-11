import logging

from broker.base import BaseOrderManager
from instruments import get_instrument_data_by_symbol
from models import Direction, OrderStatus, OrderType
from models.order import Order, OrderInputParams
from utils import get_epoch


class ICICIOrderManager(BaseOrderManager):

    def __init__(self, short_code, broker_handle):
        super().__init__("icici", broker_handle)
        self.short_code = short_code

    def place_order(self, order_input_params):
        logging.debug("%s:%s:: Going to place order with params %s", self.broker, self.short_code, order_input_params)
        breeze = self.broker_handle.broker
        order_input_params.qty = int(order_input_params.qty)
        import math

        freeze_limit = 900 if order_input_params.trading_symbol.startswith("BANK") else 1800
        isd = get_instrument_data_by_symbol(self.short_code, order_input_params.trading_symbol)
        lot_size = isd["lot_size"]
        # leg_count = max(math.ceil(orderInputParams.qty/freeze_limit), 2)
        # slice = orderInputParams.qty / leg_count
        # iceberg_quantity = math.ceil(slice / lot_size) * lot_size
        # iceberg_legs = leg_count

        if order_input_params.qty > freeze_limit and order_input_params.orderType == OrderType.MARKET:
            order_input_params.orderType = OrderType.LIMIT

        try:
            order_id = breeze.place_order(
                stock_code=isd["name"],
                # variety= breeze.VARIETY_REGULAR if orderInputParams.qty<=freeze_limit else breeze.VARIETY_ICEBERG,
                # iceberg_quantity = iceberg_quantity,
                # tradingsymbol=orderInputParams.trading_symbol,
                exchange_code=order_input_params.exchange if order_input_params.isFnO == True else breeze.EXCHANGE_NSE,
                product=self._convert_to_broker_product(order_input_params.trading_symbol),
                action=self._convert_to_broker_direction(order_input_params.direction),
                order_type=self._covert_to_broker_order(order_input_params.orderType),
                quantity=order_input_params.qty,
                price=order_input_params.price if order_input_params.orderType != OrderType.MARKET else "",
                validity="day",
                stoploss=order_input_params.triggerPrice if order_input_params.orderType == OrderType.SL_LIMIT else "",
                user_remark=order_input_params.tag[:20],
                right=self._get_instrument_right(order_input_params.trading_symbol),
                strike_price=isd["strike"],
                expiry_date=isd["expiry"],
            )

            logging.info("%s:%s:: Order placed successfully, orderId = %s with tag: %s", self.broker, self.short_code, order_id, order_input_params.tag)
            order = Order(order_input_params)
            order.orderId = order_id["Success"]["order_id"]
            order.orderPlaceTimestamp = get_epoch()
            order.lastOrderUpdateTimestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order placement in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.place_order(order_input_params)
            logging.info("%s:%s Order placement failed: %s", self.broker, self.short_code, str(order_id))
            if "price cannot be" in order_id["Error"]:
                order_input_params.orderType = OrderType.LIMIT
                return self.place_order(order_input_params)
            else:
                raise Exception(str(e))

    def modify_order(self, order, orderModifyParams, tradeQty):
        logging.info("%s:%s:: Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)

        if order.orderType == OrderType.SL_LIMIT and orderModifyParams.newTriggerPrice == order.triggerPrice:
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)
            # nothing to modify
            return order
        elif order.orderType == OrderType.LIMIT and orderModifyParams.newPrice < 0 or orderModifyParams.newPrice == order.price:
            # nothing to modify
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)
            return order

        breeze = self.broker_handle.broker
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800

        try:
            orderId = breeze.modify_order(
                order_id=order.orderId,
                exchange_code="NFO",
                quantity=int(orderModifyParams.newQty) if orderModifyParams.newQty > 0 else None,
                price=orderModifyParams.newPrice if orderModifyParams.newPrice > 0 else None,
                stoploss=orderModifyParams.newTriggerPrice if orderModifyParams.newTriggerPrice > 0 and order.orderType == OrderType.SL_LIMIT else None,
            )

            logging.info("%s:%s Order modified successfully for orderId = %s", self.broker, self.short_code, orderId)
            order.lastOrderUpdateTimestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order modification in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.modify_order(order, orderModifyParams, tradeQty)
            logging.info("%s:%s Order %s modify failed: %s", self.broker, self.short_code, order.orderId, str(e))
            raise Exception(str(e))

    def cancel_order(self, order):
        logging.debug("%s:%s Going to cancel order %s", self.broker, self.short_code, order.orderId)
        breeze = self.broker_handle.broker
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800
        try:
            orderId = breeze.cancel_order(order_id=order.orderId, exchange_code="NFO")

            logging.info("%s:%s Order cancelled successfully, orderId = %s", self.broker, self.short_code, orderId)
            order.lastOrderUpdateTimestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order cancellation in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.cancel_order(order)
            logging.info("%s:%s Order cancel failed: %s", self.broker, self.short_code, str(e))
            raise Exception(str(e))

    def fetch_update_all_orders(self, orders):
        logging.debug("%s:%s Going to fetch order book", self.broker, self.short_code)
        breeze = self.broker_handle
        orderBook = None
        try:
            orderBook = breeze.orders()
        except Exception as e:
            import traceback

            traceback.format_exc()
            logging.error("%s:%s Failed to fetch order book", self.broker, self.short_code)
            return []

        logging.debug("%s:%s Order book length = %d", self.broker, self.short_code, len(orderBook))
        numOrdersUpdated = 0
        missingOrders = []

        for bOrder in orderBook:
            foundOrder = None
            foundChildOrder = None
            parentOrder = None
            for order in orders.keys():
                if order.orderId == bOrder["order_id"]:
                    foundOrder = order
                if order.orderId == bOrder["parent_order_id"]:
                    foundChildOrder = bOrder
                    parentOrder = order

            if foundOrder != None:
                logging.debug("Found order for orderId %s", foundOrder.orderId)
                foundOrder.qty = int(bOrder["quantity"])
                foundOrder.pendingQty = int(bOrder["pending_quantity"])
                foundOrder.filledQty = foundOrder.qty - foundOrder.pendingQty

                foundOrder.orderStatus = bOrder["status"]
                if foundOrder.orderStatus == OrderStatus.CANCELLED and foundOrder.filledQty > 0:
                    # Consider this case as completed in our system as we cancel the order with pending qty when strategy stop timestamp reaches
                    foundOrder.orderStatus = OrderStatus.COMPLETE
                foundOrder.price = float(bOrder["price"])
                foundOrder.triggerPrice = float(bOrder["SLTP_price"]) if bOrder["SLTP_price"] != None else ""
                foundOrder.averagePrice = float(bOrder["average_price"])
                foundOrder.lastOrderUpdateTimestamp = bOrder["exchange_acknowledgement_date"]
                logging.debug("%s:%s:%s Updated order %s", self.broker, self.short_code, orders[foundOrder], foundOrder)
                numOrdersUpdated += 1
            elif foundChildOrder != None:
                oip = OrderInputParams(parentOrder.trading_symbol)
                oip.exchange = parentOrder.exchange
                oip.product_type = parentOrder.productType
                oip.order_type = parentOrder.orderType
                oip.price = parentOrder.price
                oip.trigger_price = parentOrder.triggerPrice
                oip.qty = parentOrder.qty
                oip.tag = parentOrder.tag
                oip.product_type = parentOrder.productType
                order = Order(oip)
                order.orderId = bOrder["order_id"]
                order.parentOrderId = parentOrder.orderId
                order.orderPlaceTimestamp = get_epoch()  # TODO should get from bOrder
                missingOrders.append(order)

        return missingOrders

    def _get_instrument_right(self, trading_symbol):
        if trading_symbol[-2:] == "PE":
            return "Put"
        elif trading_symbol[-2:] == "CE":
            return "Call"
        return "Others"

    def _convert_to_broker_product(self, trading_symbol):
        if trading_symbol[-2:] == "PE" or trading_symbol[-2:] == "CE":
            return "options"
        elif "FUT" in trading_symbol:
            return "futures"
        return "cash"

    def _covert_to_broker_order(self, orderType):
        breeze = self.broker_handle.broker
        if orderType == OrderType.LIMIT:
            return "limit"
        elif orderType == OrderType.MARKET:
            return "market"
        elif orderType == OrderType.SL_LIMIT:
            return "stoploss"
        return None

    def _convert_to_broker_direction(self, direction):
        breeze = self.broker_handle.broker
        if direction == Direction.LONG:
            return "buy"
        elif direction == Direction.SHORT:
            return "sell"
        return None

    def update_order(self, order, data):
        if order is None:
            return
        logging.info(data)
