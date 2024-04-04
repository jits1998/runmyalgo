import logging

from broker.base import BaseOrderManager
from instruments import getInstrumentDataBySymbol
from models import Direction, OrderStatus, OrderType
from models.order import Order, OrderInputParams
from utils import getEpoch


class ICICIOrderManager(BaseOrderManager):

    def __init__(self, short_code, brokerHandle):
        super().__init__("icici", brokerHandle)
        self.short_code = short_code

    def placeOrder(self, orderInputParams):
        logging.debug("%s:%s:: Going to place order with params %s", self.broker, self.short_code, orderInputParams)
        breeze = self.brokerHandle.broker
        orderInputParams.qty = int(orderInputParams.qty)
        import math

        freeze_limit = 900 if orderInputParams.tradingSymbol.startswith("BANK") else 1800
        isd = getInstrumentDataBySymbol(self.short_code, orderInputParams.tradingSymbol)
        lot_size = isd["lot_size"]
        # leg_count = max(math.ceil(orderInputParams.qty/freeze_limit), 2)
        # slice = orderInputParams.qty / leg_count
        # iceberg_quantity = math.ceil(slice / lot_size) * lot_size
        # iceberg_legs = leg_count

        if orderInputParams.qty > freeze_limit and orderInputParams.orderType == OrderType.MARKET:
            orderInputParams.orderType = OrderType.LIMIT

        try:
            orderId = breeze.place_order(
                stock_code=isd["name"],
                # variety= breeze.VARIETY_REGULAR if orderInputParams.qty<=freeze_limit else breeze.VARIETY_ICEBERG,
                # iceberg_quantity = iceberg_quantity,
                # tradingsymbol=orderInputParams.tradingSymbol,
                exchange_code=orderInputParams.exchange if orderInputParams.isFnO == True else breeze.EXCHANGE_NSE,
                product=self.convertToBrokerProductType(orderInputParams.tradingSymbol),
                action=self.convertToBrokerDirection(orderInputParams.direction),
                order_type=self.convertToBrokerOrderType(orderInputParams.orderType),
                quantity=orderInputParams.qty,
                price=orderInputParams.price if orderInputParams.orderType != OrderType.MARKET else "",
                validity="day",
                stoploss=orderInputParams.triggerPrice if orderInputParams.orderType == OrderType.SL_LIMIT else "",
                user_remark=orderInputParams.tag[:20],
                right=self.getRight(orderInputParams.tradingSymbol),
                strike_price=isd["strike"],
                expiry_date=isd["expiry"],
            )

            logging.info("%s:%s:: Order placed successfully, orderId = %s with tag: %s", self.broker, self.short_code, orderId, orderInputParams.tag)
            order = Order(orderInputParams)
            order.orderId = orderId["Success"]["order_id"]
            order.orderPlaceTimestamp = getEpoch()
            order.lastOrderUpdateTimestamp = getEpoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order placement in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.placeOrder(orderInputParams)
            logging.info("%s:%s Order placement failed: %s", self.broker, self.short_code, str(orderId))
            if "price cannot be" in orderId["Error"]:
                orderInputParams.orderType = OrderType.LIMIT
                return self.placeOrder(orderInputParams)
            else:
                raise Exception(str(e))

    def modifyOrder(self, order, orderModifyParams, tradeQty):
        logging.info("%s:%s:: Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)

        if order.orderType == OrderType.SL_LIMIT and orderModifyParams.newTriggerPrice == order.triggerPrice:
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)
            # nothing to modify
            return order
        elif order.orderType == OrderType.LIMIT and orderModifyParams.newPrice < 0 or orderModifyParams.newPrice == order.price:
            # nothing to modify
            logging.info("%s:%s:: Not Going to modify order with params %s", self.broker, self.short_code, orderModifyParams)
            return order

        breeze = self.brokerHandle.broker
        freeze_limit = 900 if order.tradingSymbol.startswith("BANK") else 1800

        try:
            orderId = breeze.modify_order(
                order_id=order.orderId,
                exchange_code="NFO",
                quantity=int(orderModifyParams.newQty) if orderModifyParams.newQty > 0 else None,
                price=orderModifyParams.newPrice if orderModifyParams.newPrice > 0 else None,
                stoploss=orderModifyParams.newTriggerPrice if orderModifyParams.newTriggerPrice > 0 and order.orderType == OrderType.SL_LIMIT else None,
            )

            logging.info("%s:%s Order modified successfully for orderId = %s", self.broker, self.short_code, orderId)
            order.lastOrderUpdateTimestamp = getEpoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order modification in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.modifyOrder(order, orderModifyParams, tradeQty)
            logging.info("%s:%s Order %s modify failed: %s", self.broker, self.short_code, order.orderId, str(e))
            raise Exception(str(e))

    def modifyOrderToMarket(self, order):
        raise Exception("Method not to be called")
        # logging.debug('%s:%s:: Going to modify order with params %s', self.broker, self.short_code)
        # breeze = self.brokerHandle.broker
        # try:
        #   orderId = breeze.modify_order(
        #     variety= breeze.VARIETY_REGULAR,
        #     order_id=order.orderId,
        #     order_type=breeze.ORDER_TYPE_MARKET)

        #   logging.info('%s:%s Order modified successfully to MARKET for orderId = %s', self.broker, self.short_code, orderId)
        #   order.lastOrderUpdateTimestamp = Utils.getEpoch()
        #   return order
        # except Exception as e:
        #   logging.info('%s:%s Order modify to market failed: %s', self.broker, self.short_code, str(e))
        #   raise Exception(str(e))

    def cancelOrder(self, order):
        logging.debug("%s:%s Going to cancel order %s", self.broker, self.short_code, order.orderId)
        breeze = self.brokerHandle.broker
        freeze_limit = 900 if order.tradingSymbol.startswith("BANK") else 1800
        try:
            orderId = breeze.cancel_order(order_id=order.orderId, exchange_code="NFO")

            logging.info("%s:%s Order cancelled successfully, orderId = %s", self.broker, self.short_code, orderId)
            order.lastOrderUpdateTimestamp = getEpoch()
            return order
        except Exception as e:
            if "Too many requests" in str(e):
                logging.info("%s:%s retrying order cancellation in 1 s for %s", self.broker, self.short_code, order.orderId)
                import time

                time.sleep(1)
                self.cancelOrder(order)
            logging.info("%s:%s Order cancel failed: %s", self.broker, self.short_code, str(e))
            raise Exception(str(e))

    def fetchAndUpdateAllOrderDetails(self, orders):
        logging.debug("%s:%s Going to fetch order book", self.broker, self.short_code)
        breeze = self.brokerHandle
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
                oip = OrderInputParams(parentOrder.tradingSymbol)
                oip.exchange = parentOrder.exchange
                oip.productType = parentOrder.productType
                oip.orderType = parentOrder.orderType
                oip.price = parentOrder.price
                oip.triggerPrice = parentOrder.triggerPrice
                oip.qty = parentOrder.qty
                oip.tag = parentOrder.tag
                oip.productType = parentOrder.productType
                order = Order(oip)
                order.orderId = bOrder["order_id"]
                order.parentOrderId = parentOrder.orderId
                order.orderPlaceTimestamp = getEpoch()  # TODO should get from bOrder
                missingOrders.append(order)

        return missingOrders

    def getRight(self, tradingSymbol):
        if tradingSymbol[-2:] == "PE":
            return "Put"
        elif tradingSymbol[-2:] == "CE":
            return "Call"
        return "Others"

    def convertToBrokerProductType(self, tradingSymbol):
        if tradingSymbol[-2:] == "PE" or tradingSymbol[-2:] == "CE":
            return "options"
        elif "FUT" in tradingSymbol:
            return "futures"
        return "cash"

    def convertToBrokerOrderType(self, orderType):
        breeze = self.brokerHandle.broker
        if orderType == OrderType.LIMIT:
            return "limit"
        elif orderType == OrderType.MARKET:
            return "market"
        elif orderType == OrderType.SL_LIMIT:
            return "stoploss"
        return None

    def convertToBrokerDirection(self, direction):
        breeze = self.brokerHandle.broker
        if direction == Direction.LONG:
            return "buy"
        elif direction == Direction.SHORT:
            return "sell"
        return None

    def updateOrder(self, order, data):
        if order is None:
            return
        logging.info(data)
