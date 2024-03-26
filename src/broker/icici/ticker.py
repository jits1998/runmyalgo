import logging

import socketio  # type: ignore[import-untyped]

from broker import BaseTicker
from models import TickData

from instruments import getInstrumentDataByToken, getInstrumentDataBySymbol


class ICICITicker(BaseTicker):
    def __init__(self, short_code, brokerHandler):
        super().__init__(short_code, brokerHandler)

    def startTicker(self, appKey, accessToken):
        if accessToken == None:
            logging.error("ICICITicker startTicker: Cannot start ticker as accessToken is empty")
            return

        # self.brokerLogin.getBrokerHandle().broker.

        ticker = self.brokerHandler.broker

        logging.info("ICICITicker: Going to connect..")
        self.ticker = ticker
        try:

            self.ticker.ws_connect()

            def on_ticks(bTick):
                # convert broker specific Ticks to our system specific Ticks (models.TickData) and pass to super class function
                ticks = []
                isd = getInstrumentDataByToken(self.short_code, bTick["symbol"][4:])
                tradingSymbol = isd["tradingsymbol"]
                tick = TickData(tradingSymbol)
                tick.lastTradedPrice = bTick["last"]
                if not isd["segment"] == "INDICES":
                    tick.lastTradedQuantity = bTick["ltq"]
                    tick.avgTradedPrice = bTick["avgPrice"]
                    tick.volume = bTick["ttq"]
                    tick.totalBuyQuantity = bTick["totalBuyQt"]
                    tick.totalSellQuantity = bTick["totalSellQ"]
                # else:
                #   tick.exchange_timestamp = bTick['exchange_timestamp']
                tick.open = bTick["open"]
                tick.high = bTick["high"]
                tick.low = bTick["low"]
                tick.close = bTick["close"]
                tick.change = bTick["change"]
                ticks.append(tick)
                self.onNewTicks(ticks)

            # ticker.subscribe_feeds(get_order_notification=True)
            self.ticker.on_ticks = on_ticks
        except socketio.exceptions.ConnectionError as e:
            if str(e) == "Already connected":
                return
            else:
                raise e

    def stopTicker(self):
        logging.info("ICICITicker: stopping..")
        self.ticker.close(1000, "Manual close")

    def registerSymbols(self, symbols, mode=None):
        # breeze.subscribe_feeds(stock_token="1.1!500780")
        tokens = []
        for symbol in symbols:
            isd = getInstrumentDataBySymbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker registerSymbol: %s token = %s", symbol, token)
            print(self.ticker.subscribe_feeds(stock_token="4.1!" + token))
            tokens.append(token)

        logging.debug("ICICITicker Subscribing tokens %s", tokens)

    def unregisterSymbols(self, symbols):
        tokens = []
        for symbol in symbols:
            isd = getInstrumentDataBySymbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker unregisterSymbols: %s token = %s", symbol, token)
            tokens.append(token)

        logging.info("ICICITicker Unsubscribing tokens %s", tokens)
        self.ticker.unsubscribe(tokens)
