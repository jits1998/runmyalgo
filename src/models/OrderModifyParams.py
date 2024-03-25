from typing import Type

from models import OrderType


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
