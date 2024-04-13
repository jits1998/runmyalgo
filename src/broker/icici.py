import csv
import logging
import urllib
from io import BytesIO, TextIOWrapper
from typing import Dict, List
from urllib.request import urlopen, urlretrieve
from zipfile import ZipFile

import dateutil.parser
import socketio  # type: ignore[import-untyped]
from breeze_connect import BreezeConnect  # type: ignore[import-untyped]
from breeze_connect import config as breeze_config

from broker import brokers, tickers
from broker.base import Broker as Base
from broker.base import Ticker as BaseTicker
from config import get_system_config
from core import Quote
from instruments import get_instrument_data_by_symbol, get_instrument_data_by_token
from models import TickData
from models.order import Order, OrderInputParams, OrderModifyParams


class Broker(Base[BreezeConnect]):

    def login(self, args: Dict) -> str:
        logging.info("==> ICICILogin .args => %s", args)
        self.system_config = get_system_config()
        self.broker_handle = BreezeConnect(api_key=self.user_details["key"])
        redirect_url = None
        if "apisession" in args:

            apisession = args["apisession"]

            logging.info("ICICI apisession = %s", apisession)

            self.set_access_token(apisession)

            if not self.broker_handle.user_id == self.user_details["client_id"]:
                raise Exception("Invalid User Credentials")

            logging.info("ICICI Login successful. apisession = %s", apisession)

            homeUrl = self.system_config["homeUrl"]
            logging.info("ICICI Redirecting to home page %s", homeUrl)

            redirect_url = homeUrl
        else:
            redirect_url = "https://api.icicidirect.com/apiuser/login?api_key=" + urllib.parse.quote_plus(self.user_details["key"])

        return redirect_url

    def place_order(self, order_input_params: OrderInputParams) -> bool:
        return False

    def modify_order(self, order: Order, order_modify_params: OrderModifyParams) -> bool:
        return False

    def cancel_order(self, order: Order) -> bool:
        return False

    def fetch_update_all_orders(self, orders: List[Order]) -> None: ...

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        return Quote(trading_symbol)

    def get_index_quote(self, trading_symbol: str, short_code: str, exchange: str = "NSE") -> Quote:
        return Quote(trading_symbol)

    def margins(self) -> List:
        return []

    def positions(self) -> List:
        return []

    def orders(self) -> List:
        return []

    def quote(self, key: str) -> Dict:
        return {}

    def instruments(self, exchange: str) -> List:
        # get instruments file to get tradesymbols
        trading_symbolDict = {}
        f, _ = urlretrieve("https://api.kite.trade/instruments")
        with open(f, newline="") as csvfile:
            r = csv.DictReader(csvfile)
            for row in r:
                trading_symbolDict[row["exchange_token"]] = row["tradingsymbol"]

        resp = urlopen(breeze_config.SECURITY_MASTER_URL)
        zipfile = ZipFile(BytesIO(resp.read()))
        mapper_exchangecode_to_file = breeze_config.ISEC_NSE_CODE_MAP_FILE

        if exchange == "NFO":
            exchange = "fonse"

        file_key = mapper_exchangecode_to_file.get(exchange.lower())

        records: List = []

        if file_key is None:
            return records

        with zipfile.open(file_key) as required_file:

            # field_names={'nse':['Token', 'ShortName', 'Series', 'CompanyName', 'ticksize', 'Lotsize',
            #              'DateOfListing', 'DateOfDeListing', 'IssuePrice', 'FaceValue', 'ISINCode',
            #              '52WeeksHigh', '52WeeksLow', 'LifeTimeHigh', 'LifeTimeLow', 'HighDate',
            #              'LowDate', 'Symbol', 'InstrumentType', 'PermittedToTrade', 'IssueCapital',
            #              'WarningPercent', 'FreezePercent', 'CreditRating', 'IssueRate', 'IssueStartDate',
            #             'InterestPaymentDate', 'IssueMaturityDate', 'BoardLotQty', 'Name', 'ListingDate',
            #             'ExpulsionDate', 'ReAdmissionDate', 'RecordDate', 'ExpiryDate', 'NoDeliveryStartDate',
            #             'NoDeliveryEndDate', 'MFill', 'AON', 'ParticipantInMarketIndex', 'BookClsStartDate',
            #             'NoDeliveryEndDate', 'MFill', 'AON', 'ParticipantInMarketIndex', 'BookClsStartDate',
            #             'BookClsEndDate', 'EGM', 'AGM', 'Interest', 'Bonus', 'Rights', 'Dividends',
            #             'LocalUpdateDateTime', 'DeleteFlag', 'Remarks', 'NormalMarketStatus', 'OddLotMarketStatus',
            #             'SpotMarketStatus', 'AuctionMarketStatus', 'NormalMarketEligibility', 'OddLotlMarketEligibility',
            #             'SpotMarketEligibility', 'AuctionlMarketEligibility', 'MarginPercentage', 'ExchangeCode'],
            #             'bse':None,
            #             'fonse': None}
            reader = csv.DictReader(TextIOWrapper(required_file, "utf-8"))

            for row in reader:
                instrument = {}
                if reader.line_num == 1:
                    continue

                if exchange.lower() == "nse" and row[' "Series"'] in ["EQ", "0"]:
                    instrument["exchange_token"] = row["Token"]
                    instrument["tradingsymbol"] = row[' "ExchangeCode"'] if row[' "Series"'] not in ["0"] else row["Token"]
                    instrument["instrument_token"] = row["Token"]
                    instrument["name"] = row[' "ShortName"']
                    instrument["last_price"] = 0.0
                    instrument["expiry"] = row[' "ExpiryDate"']
                    instrument["strike"] = 0
                    instrument["tick_size"] = float(row[' "ticksize"'])
                    instrument["lot_size"] = int(row[' "Lotsize"'])
                    instrument["instrument_type"] = "EQ"
                    instrument["segment"] = "NSE" if row[' "Series"'] not in ["0"] else "INDICES"
                    instrument["exchange"] = "NSE"
                    records.append(instrument)
                elif exchange.lower() == "fonse":
                    # row["last_price"] = float(row["last_price"])
                    # row["strike"] = float(row["strike"])
                    # row["tick_size"] = float(row["tick_size"])
                    # row["lot_size"] = int(row["lot_size"])

                    instrument["exchange_token"] = row["Token"]
                    instrument["tradingsymbol"] = trading_symbolDict.get(instrument["exchange_token"], None)
                    if instrument["tradingsymbol"] is None:
                        continue
                    instrument["instrument_token"] = row["Token"]
                    instrument["name"] = row["ShortName"]
                    instrument["last_price"] = 0.0
                    instrument["expiry"] = row["ExpiryDate"]
                    instrument["strike"] = row["StrikePrice"]
                    instrument["tick_size"] = float(row["TickSize"])
                    instrument["lot_size"] = int(row["LotSize"])
                    instrument["instrument_type"] = row["OptionType"] if row["OptionType"] != "XX" else "FUT"
                    instrument["segment"] = "NFO-" + row["Series"][:3]
                    instrument["exchange"] = "NFO"
                    # Parse date
                    if len(instrument["expiry"]) == 10:
                        instrument["expiry"] = dateutil.parser.parse(instrument["expiry"]).date()
                    records.append(instrument)
                else:
                    pass

        return records

    def set_access_token(self, access_token) -> None:
        try:
            super().set_access_token(access_token)
            self.broker_handle.generate_session(session_token=access_token, api_secret=self.user_details["secret"])
        except Exception as e:
            raise Exception("can't generate session as {}, clear web session".format(str(e)))


class Ticker(BaseTicker[Broker]):

    def __init__(self, short_code, broker_handler: Broker):
        super().__init__(short_code, broker_handler)

    def start_ticker(self):

        ticker = self.broker.broker_handle

        logging.info("ICICI Ticker: Going to connect..")
        self.ticker = ticker
        try:

            self.ticker.ws_connect()

            def on_ticks(bTick):
                logging.debug(bTick["symbol"] + " => " + str(bTick["last"]))
                # convert broker specific Ticks to our system specific Ticks (models.TickData) and pass to super class function
                ticks = []
                isd = get_instrument_data_by_token(self.short_code, bTick["symbol"][4:])
                trading_symbol = isd["tradingsymbol"]
                tick = TickData(trading_symbol)
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
                self.on_new_ticks(ticks)

            # ticker.subscribe_feeds(get_order_notification=True)
            self.ticker.on_ticks = on_ticks
        except socketio.exceptions.ConnectionError as e:
            if str(e) == "Already connected":
                return
            else:
                raise e

    def stop_ticker(self):
        logging.info("ICICITicker: stopping..")
        self.ticker.close(1000, "Manual close")

    def register_symbols(self, symbols, mode=None):
        # breeze.subscribe_feeds(stock_token="1.1!500780")
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker registerSymbol: %s token = %s", symbol, token)
            print(self.ticker.subscribe_feeds(stock_token="4.1!" + token))
            tokens.append(token)

        logging.debug("ICICITicker Subscribing tokens %s", tokens)

    def unregister_symbols(self, symbols):
        tokens = []
        for symbol in symbols:
            isd = get_instrument_data_by_symbol(self.short_code, symbol)
            token = isd["instrument_token"]
            logging.debug("ICICITicker unregisterSymbols: %s token = %s", symbol, token)
            tokens.append(token)

        logging.info("ICICITicker Unsubscribing tokens %s", tokens)
        self.ticker.unsubscribe(tokens)


brokers["icici"] = Broker
tickers["icici"] = Ticker
