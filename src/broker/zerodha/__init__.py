from broker import brokers
from broker.zerodha.handler import ZerodhaHandler as Handler
from broker.zerodha.login import ZerodhaLogin as Login
from broker.zerodha.ticker import ZerodhaTicker as Ticker

brokers["zerodha"] = {}
brokers["zerodha"]["LoginHandler"] = Login
brokers["zerodha"]["ticker"] = Ticker
