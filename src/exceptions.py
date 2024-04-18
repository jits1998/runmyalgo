class DisableTradeException(Exception):
    def __init__(self, message: str):
        """Initialize the exception."""
        super(Exception, self).__init__(message)


class DeRegisterStrategyException(Exception):
    def __init__(self, message: str):
        """Initialize the exception."""
        super(Exception, self).__init__(message)
