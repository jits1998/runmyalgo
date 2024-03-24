from broker import brokers
from broker.zerodha.ZerodhaLoginHandler import ZerodhaLoginHandler

brokers["zerodha"] = {}
brokers["zerodha"]["LoginHandler"] = ZerodhaLoginHandler
