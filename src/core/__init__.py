from datetime import datetime, timedelta
from json import JSONEncoder


class Quote:
    def __init__(self, trading_symbol: str) -> None:
        self.trading_symbol = trading_symbol
        self.lastTradedPrice = 0
        self.lastTradedQuantity = 0
        self.avgTradedPrice = 0
        self.volume = 0
        self.totalBuyQuantity = 0
        self.totalSellQuantity = 0
        self.open = 0
        self.high = 0
        self.low = 0
        self.close = 0
        self.change = 0
        self.oiDayHigh = 0
        self.oiDayLow = 0
        self.lowerCiruitLimit = 0
        self.upperCircuitLimit = 0
        self.oi = 0
