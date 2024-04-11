from broker import brokers
from broker.zerodha.handler import ZerodhaHandler as Handler
from broker.zerodha.login import ZerodhaLogin as Login
from broker.zerodha.order_manager import ZerodhaOrderManager as OrderManager
from broker.zerodha.ticker import ZerodhaTicker as Ticker

brokers["zerodha"] = {}
brokers["zerodha"]["LoginHandler"] = Login
brokers["zerodha"]["ticker"] = Ticker
brokers["zerodha"]["order_manager"] = OrderManager
