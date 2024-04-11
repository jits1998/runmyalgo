import logging

from broker.base import BaseOrderManager
from instruments import get_instrument_data_by_symbol
from models import Direction, OrderStatus, OrderType, ProductType
from models.order import Order, OrderInputParams
from utils import get_epoch


class ZerodhaOrderManager(BaseOrderManager):

    def __init__(self, short_code, broker_handle):
        super().__init__("zerodha", broker_handle)
        self.short_code = short_code

    def place_order(self, orderInputParams):
        logging.debug("%s:%s:: Going to place order with params %s", self.broker, self.short_code, orderInputParams)
        kite = self.broker_handle
        orderInputParams.qty = int(orderInputParams.qty)
        import math

        freeze_limit = 900 if orderInputParams.trading_symbol.startswith("BANK") else 1800
        lot_size = get_instrument_data_by_symbol(self.short_code, orderInputParams.trading_symbol)["lot_size"]
        leg_count = max(math.ceil(orderInputParams.qty / freeze_limit), 2)
        slice = orderInputParams.qty / leg_count
        iceberg_quantity = math.ceil(slice / lot_size) * lot_size
        iceberg_legs = leg_count

        if orderInputParams.qty > freeze_limit and orderInputParams.orderType == OrderType.MARKET:
            orderInputParams.orderType = OrderType.LIMIT

        try:
            orderId = kite.place_order(
                variety=kite.VARIETY_REGULAR if orderInputParams.qty <= freeze_limit else kite.VARIETY_ICEBERG,
                iceberg_legs=iceberg_legs,
                iceberg_quantity=iceberg_quantity,
                exchange=orderInputParams.exchange if orderInputParams.isFnO == True else kite.EXCHANGE_NSE,
                tradingsymbol=orderInputParams.trading_symbol,
                transaction_type=self.convert_to_broker_direction(orderInputParams.direction),
                quantity=orderInputParams.qty,
                price=orderInputParams.price,
                trigger_price=orderInputParams.triggerPrice,
                product=self.convert_to_broker_product(orderInputParams.productType),
                order_type=self.covert_to_broker_order(orderInputParams.orderType),
                tag=orderInputParams.tag[:20],
            )

            logging.info("%s:%s:: Order placed successfully, orderId = %s with tag: %s", self.broker, self.short_code, orderId, orderInputParams.tag)
            order = Order(orderInputParams)
            order.orderId = orderId
            order.orderPlaceTimestamp = get_epoch()
            order.lastOrderUpdateTimestamp = get_epoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order placement in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.place_order(orderInputParams)
            logging.info("%s:%s Order placement failed: %s", self.broker, self.short_code, str(e))
            if "Trigger price for stoploss" in str(e):
                orderInputParams.orderType = OrderType.LIMIT
                return self.place_order(orderInputParams)
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

        kite = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800

        try:
            orderId = kite.modify_order(
                variety=kite.VARIETY_REGULAR if tradeQty <= freeze_limit else kite.VARIETY_ICEBERG,
                order_id=order.orderId,
                quantity=int(orderModifyParams.newQty) if orderModifyParams.newQty > 0 else None,
                price=orderModifyParams.newPrice if orderModifyParams.newPrice > 0 else None,
                trigger_price=orderModifyParams.newTriggerPrice if orderModifyParams.newTriggerPrice > 0 else None,
                order_type=orderModifyParams.newOrderType if orderModifyParams.newOrderType != None else None,
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

    def modifyOrderToMarket(self, order):
        raise Exception("Method not to be called")
        # logging.debug('%s:%s:: Going to modify order with params %s', self.broker, self.short_code)
        # kite = self.broker_handle
        # try:
        #   orderId = kite.modify_order(
        #     variety= kite.VARIETY_REGULAR,
        #     order_id=order.orderId,
        #     order_type=kite.ORDER_TYPE_MARKET)

        #   logging.info('%s:%s Order modified successfully to MARKET for orderId = %s', self.broker, self.short_code, orderId)
        #   order.lastOrderUpdateTimestamp = getEpoch()
        #   return order
        # except Exception as e:
        #   logging.info('%s:%s Order modify to market failed: %s', self.broker, self.short_code, str(e))
        #   raise Exception(str(e))

    def cancel_order(self, order):
        logging.debug("%s:%s Going to cancel order %s", self.broker, self.short_code, order.orderId)
        kite = self.broker_handle
        freeze_limit = 900 if order.trading_symbol.startswith("BANK") else 1800
        try:
            orderId = kite.cancel_order(variety=kite.VARIETY_REGULAR if order.qty <= freeze_limit else kite.VARIETY_ICEBERG, order_id=order.orderId)

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
        kite = self.broker_handle
        orderBook = None
        try:
            orderBook = kite.orders()
        except Exception as e:
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
                foundOrder.qty = bOrder["quantity"]
                foundOrder.filledQty = bOrder["filled_quantity"]
                foundOrder.pendingQty = bOrder["pending_quantity"]
                foundOrder.orderStatus = bOrder["status"]
                if foundOrder.orderStatus == OrderStatus.CANCELLED and foundOrder.filledQty > 0:
                    # Consider this case as completed in our system as we cancel the order with pending qty when strategy stop timestamp reaches
                    foundOrder.orderStatus = OrderStatus.COMPLETE
                foundOrder.price = bOrder["price"]
                foundOrder.triggerPrice = bOrder["trigger_price"]
                foundOrder.averagePrice = bOrder["average_price"]
                foundOrder.lastOrderUpdateTimestamp = bOrder["exchange_update_timestamp"]
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

    def convert_to_broker_product(self, productType):
        kite = self.broker_handle
        if productType == ProductType.MIS:
            return kite.PRODUCT_MIS
        elif productType == ProductType.NRML:
            return kite.PRODUCT_NRML
        elif productType == ProductType.CNC:
            return kite.PRODUCT_CNC
        return None

    def covert_to_broker_order(self, orderType):
        kite = self.broker_handle
        if orderType == OrderType.LIMIT:
            return kite.ORDER_TYPE_LIMIT
        elif orderType == OrderType.MARKET:
            return kite.ORDER_TYPE_MARKET
        elif orderType == OrderType.SL_MARKET:
            return kite.ORDER_TYPE_SLM
        elif orderType == OrderType.SL_LIMIT:
            return kite.ORDER_TYPE_SL
        return None

    def convert_to_broker_direction(self, direction):
        kite = self.broker_handle
        if direction == Direction.LONG:
            return kite.TRANSACTION_TYPE_BUY
        elif direction == Direction.SHORT:
            return kite.TRANSACTION_TYPE_SELL
        return None

    def updateOrder(self, order, data):
        if order is None:
            return
        logging.info(data)
