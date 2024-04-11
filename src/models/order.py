from models import Direction, OrderType, ProductType, Segment


class Order:
    def __init__(self, orderInputParams=None):
        self.trading_symbol = orderInputParams.trading_symbol if orderInputParams != None else ""
        self.exchange = orderInputParams.exchange if orderInputParams != None else "NSE"
        self.productType = orderInputParams.productType if orderInputParams != None else ""
        self.orderType = orderInputParams.orderType if orderInputParams != None else ""  # LIMIT/MARKET/SL-LIMIT/SL-MARKET
        self.price = orderInputParams.price if orderInputParams != None else 0
        self.triggerPrice = orderInputParams.triggerPrice if orderInputParams != None else 0  # Applicable in case of SL orders
        self.qty = orderInputParams.qty if orderInputParams != None else 0
        self.tag = orderInputParams.tag if orderInputParams != None else None
        self.orderId = ""  # The order id received from broker after placing the order
        self.orderStatus = None  # One of the status defined in ordermgmt.OrderStatus
        self.averagePrice = 0  # Average price at which the order is filled
        self.filledQty = 0  # Filled quantity
        self.pendingQty = 0  # Qty - Filled quantity
        self.orderPlaceTimestamp = None  # Timestamp when the order is placed
        self.lastOrderUpdateTimestamp = None  # Applicable if you modify the order Ex: Trailing SL
        self.message = None  # In case any order rejection or any other error save the response from broker in this field
        self.parentOrderId = None

    def __str__(self):
        return (
            "orderId="
            + str(self.orderId)
            + ", orderStatus="
            + str(self.orderStatus)
            + ", symbol="
            + str(self.trading_symbol)
            + ", productType="
            + str(self.productType)
            + ", orderType="
            + str(self.orderType)
            + ", price="
            + str(self.price)
            + ", triggerPrice="
            + str(self.triggerPrice)
            + ", qty="
            + str(self.qty)
            + ", filledQty="
            + str(self.filledQty)
            + ", pendingQty="
            + str(self.pendingQty)
            + ", averagePrice="
            + str(self.averagePrice)
        )


class OrderInputParams:
    exchange: str = "NSE"  # default
    is_fno: bool = False
    segment: Segment = Segment.EQUITY  # default
    product_type: ProductType = ProductType.MIS  # default
    trading_symbol: str
    direction: Direction
    order_type: OrderType
    qty: int
    price: float
    trigger_price: float  # Applicable in case of SL order
    tag: str

    def __init__(self, trading_symbol):
        self.trading_symbol = trading_symbol

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
