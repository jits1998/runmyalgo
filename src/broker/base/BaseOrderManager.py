class BaseOrderManager:
    def __init__(self, broker, brokerHandle):
        self.broker = broker
        self.brokerHandle = brokerHandle

    def placeOrder(self, orderInputParams):
        pass

    def modifyOrder(self, order, orderModifyParams):
        pass

    def modifyOrderToMarket(self, order):
        pass

    def cancelOrder(self, order):
        pass

    def fetchAndUpdateAllOrderDetails(self, orders):
        pass

    def convertToBrokerProductType(self, productType):
        return productType

    def convertToBrokerOrderType(self, orderType):
        return orderType

    def convertToBrokerDirection(self, direction):
        return direction
