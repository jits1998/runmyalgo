from broker import brokers
from broker.icici.handler import ICICIHandler
from broker.icici.login import ICICILogin
from broker.icici.ticker import ICICITicker

brokers["icici"] = {}
brokers["icici"]["LoginHandler"] = ICICILogin
brokers["icici"]["ticker"] = ICICITicker
