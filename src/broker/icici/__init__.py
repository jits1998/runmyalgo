from broker import brokers
from broker.icici.handler import ICICIHandler as Handler
from broker.icici.login import ICICILogin as Login
from broker.icici.order_manager import ICICIOrderManager as OrderManager
from broker.icici.ticker import ICICITicker as Ticker

brokers["icici"] = {}
brokers["icici"]["LoginHandler"] = Login
brokers["icici"]["ticker"] = Ticker
brokers["icici"]["order_manager"] = OrderManager
