from models import Direction, OrderType, ProductType, Segment


class OrderInputParams:

    def __init__(self, trading_symbol: str) -> None:
        self.trading_symbol = trading_symbol
        self.exchange: str = "NSE"  # default
        self.is_fno: bool = False
        self.segment: Segment = Segment.EQUITY  # default
        self.product_type: ProductType = ProductType.MIS  # default
        self.direction: Direction = Direction.LONG
        self.order_type: OrderType = OrderType.LIMIT
        self.qty: int = 0
        self.price: float = 0.0
        self.trigger_price: float = 0.0  # Applicable in case of SL order
        self.tag: str = ""

    def __str__(self):
        return (
            "symbol="
            + self.trading_symbol
            + ", exchange="
            + self.exchange
            + ", productType="
            + self.product_type
            + ", segment="
            + self.segment
            + ", direction="
            + self.direction
            + ", orderType="
            + self.order_type
            + ", qty="
            + str(self.qty)
            + ", price="
            + str(self.price)
            + ", triggerPrice="
            + str(self.trigger_price)
            + ", isFnO="
            + str(self.is_fno)
        )


class OrderModifyParams:

    newPrice: float
    newTriggerPrice: float  # Applicable in case of SL order
    newQty: int
    # Ex: Can change LIMIT order to SL order or vice versa. Not supported by all brokers
    newOrderType: OrderType

    def __init__(self):
        pass

    def __str__(self):
        return (
            "newPrice="
            + str(self.newPrice)
            + ", newTriggerPrice="
            + str(self.newTriggerPrice)
            + ", newQty="
            + str(self.newQty)
            + ", newOrderType="
            + str(self.newOrderType)
        )


class Order:
    def __init__(self, orderInputParams: OrderInputParams):
        self.trading_symbol = orderInputParams.trading_symbol if orderInputParams != None else ""
        self.exchange = orderInputParams.exchange if orderInputParams != None else "NSE"
        self.product_type = orderInputParams.product_type if orderInputParams != None else ""
        self.order_type = orderInputParams.order_type if orderInputParams != None else ""  # LIMIT/MARKET/SL-LIMIT/SL-MARKET
        self.price = orderInputParams.price if orderInputParams != None else 0
        self.trigger_price = orderInputParams.trigger_price if orderInputParams != None else 0  # Applicable in case of SL orders
        self.qty = orderInputParams.qty if orderInputParams != None else 0
        self.tag = orderInputParams.tag if orderInputParams != None else None
        self.order_id = ""  # The order id received from broker after placing the order
        self.order_status = None  # One of the status defined in ordermgmt.OrderStatus
        self.average_price = 0  # Average price at which the order is filled
        self.filled_qty = 0  # Filled quantity
        self.pending_qty = 0  # Qty - Filled quantity
        self.place_timestamp = None  # Timestamp when the order is placed
        self.update_timestamp = None  # Applicable if you modify the order Ex: Trailing SL
        self.message = None  # In case any order rejection or any other error save the response from broker in this field
        self.parent_order_id = None

    def __str__(self):
        return (
            "orderId="
            + str(self.order_id)
            + ", orderStatus="
            + str(self.order_status)
            + ", symbol="
            + str(self.trading_symbol)
            + ", productType="
            + str(self.product_type)
            + ", orderType="
            + str(self.order_type)
            + ", price="
            + str(self.price)
            + ", triggerPrice="
            + str(self.trigger_price)
            + ", qty="
            + str(self.qty)
            + ", filledQty="
            + str(self.filled_qty)
            + ", pendingQty="
            + str(self.pending_qty)
            + ", averagePrice="
            + str(self.average_price)
        )
