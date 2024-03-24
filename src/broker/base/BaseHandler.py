class BaseHandler:
    def __init__(self, broker):
        self.broker = broker

    def set_access_token():
        raise Exception("Method not to be called")

    def margins(self):
        raise Exception("Method not to be called")

    def positions(self):
        raise Exception("Method not to be called")

    def orders(self):
        raise Exception("Method not to be called")

    def quote(self, key):
        raise Exception("Method not to be called")

    def instruments(self, exchange):
        raise Exception("Method not to be called")

    def getBrokerHandle(self):
        return self.broker
