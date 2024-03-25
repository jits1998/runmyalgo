from broker import brokers
from broker.icici.ICICIHandler import ICICIHandler
from broker.icici.ICICILogin import ICICILogin

brokers["icici"] = {}
brokers["icici"]["LoginHandler"] = ICICILogin
