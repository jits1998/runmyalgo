class DisableTradeException(Exception):
    def __init__(self, message):
        """Initialize the exception."""
        super(Exception, self).__init__(message=message)


class DeRegisterStrategyException(Exception):
    def __init__(self, message):
        """Initialize the exception."""
        super(Exception, self).__init__(message)
