class BaseLogin:

    def __init__(self, userDetails):
        self.userDetails = userDetails
        self.broker = userDetails.broker
        self.accessToken = None

    # Derived class should implement login function and return redirect url
    def login(self, args):
        pass

    def setBrokerHandle(self, brokerHandle):
        self.brokerHandle = brokerHandle

    def setAccessToken(self, accessToken):
        self.accessToken = accessToken

    def getUserDetails(self):
        return self.userDetails

    def getAccessToken(self):
        return self.accessToken

    def getBrokerHandle(self):
        return self.brokerHandle
