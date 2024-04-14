from datetime import datetime
from json import JSONEncoder


class Quote:
    def __init__(self, trading_symbol: str) -> None:
        self.trading_symbol = trading_symbol
        self.last_traded_price = 0
        self.last_traded_quantity = 0
        self.avg_traded_price = 0
        self.volume = 0
        self.total_buy_quantity = 0
        self.total_sell_quantity = 0
        self.open = 0
        self.high = 0
        self.low = 0
        self.close = 0
        self.change = 0
        self.oi_day_high = 0
        self.oi_day_low = 0
        self.lower_ciruit_limit = 0
        self.upper_circuit_limit = 0
        self.oi = 0
