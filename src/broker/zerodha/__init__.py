from broker import brokers
from broker.zerodha.handler import ZerodhaHandler
from broker.zerodha.login import ZerodhaLogin
from broker.zerodha.ticker import ZerodhaTicker

brokers["zerodha"] = {}
brokers["zerodha"]["LoginHandler"] = ZerodhaLogin
brokers["zerodha"]["ticker"] = ZerodhaTicker
