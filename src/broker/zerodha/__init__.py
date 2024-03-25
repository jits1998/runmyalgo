from broker import brokers
from broker.zerodha.ZerodhaHandler import ZerodhaHandler
from broker.zerodha.ZerodhaLogin import ZerodhaLogin

brokers["zerodha"] = {}
brokers["zerodha"]["LoginHandler"] = ZerodhaLogin
