from typing import Type

from models import Direction, OrderType, ProductType, Segment


class OrderInputParams:
    exchange: str = "NSE"  # default
    isFnO: bool = False
    segment: Segment = Segment.EQUITY  # default
    productType: ProductType = ProductType.MIS  # default
    tradingSymbol: str
    direction: Direction
    orderType: OrderType
    qty: int
    price: float
    triggerPrice: float  # Applicable in case of SL order
    tag: str

    def __init__(self, tradingSymbol):
        self.tradingSymbol = tradingSymbol

    def __str__(self):
        return (
            "symbol="
            + self.tradingSymbol
            + ", exchange="
            + self.exchange
            + ", productType="
            + self.productType
            + ", segment="
            + self.segment
            + ", direction="
            + self.direction
            + ", orderType="
            + self.orderType
            + ", qty="
            + str(self.qty)
            + ", price="
            + str(self.price)
            + ", triggerPrice="
            + str(self.triggerPrice)
            + ", isFnO="
            + str(self.isFnO)
        )
