import csv
import datetime
import logging
import time
from io import BytesIO, TextIOWrapper
from urllib.request import urlopen, urlretrieve
from zipfile import ZipFile

import dateutil.parser
import requests
from breeze_connect import config as breeze_config  # type: ignore[import-untyped]

from broker import BaseHandler
from core import Quote
from instruments import get_instrument_data_by_symbol
from models import OrderStatus


class ICICIHandler(BaseHandler):

    def __init__(self, broker_handle, config):
        super().__init__(broker_handle)
        self.broker_handle = broker_handle
        self.config = config

    def set_access_token(self, access_token):
        try:
            self.broker_handle.generate_session(session_token=access_token, api_secret=self.config["secret"])
        except Exception as e:
            raise Exception("can't generate session as {}, clear web session".format(str(e)))

    def margins(self):
        margins = self.broker_handle.get_margin(exchange_code="NFO")

        return margins

    def positions(self):
        raise Exception("Method not to be called")

    def orders(self):
        order_list = self.broker_handle.get_order_list(
            exchange_code="NFO",
            from_date=datetime.datetime.now().isoformat()[:10] + "T05:30:00.000Z",
            to_date=datetime.datetime.now().isoformat()[:10] + "T05:30:00.000Z",
        )["Success"]

        if order_list == None:
            return []
        else:
            for order in order_list:
                if order["status"] == "Executed":
                    order["status"] = OrderStatus.COMPLETE
                order["tradingsymbol"] = [
                    x
                    for x in self.instruments
                    if x["name"] == order["stock_code"]
                    and x["strike"] == str(order["strike_price"]).split(".")[0]
                    and x["expiry"] == order["expiry_date"]
                    and x["instrument_type"] == ("PE" if order["right"] == "Put" else "CE")
                ][0]["tradingsymbol"]
                order["tag"] = order["user_remark"]
                order["transaction_type"] = order["action"]
        return order_list

    def _quote(self, isd):
        product_type = ""
        right = ""
        retry = False
        if isd["instrument_type"] == "PE":
            product_type = "options"
            right = "PUT"
        elif isd["instrument_type"] == "CE":
            product_type = "options"
            right = "CALL"
        elif isd["expiry"] != "":
            product_type = "futures"
            right = "Others"

        try:
            return self.broker_handle.get_quotes(
                stock_code=isd["name"],
                exchange_code=isd["exchange"],
                expiry_date=isd["expiry"],
                product_type=product_type,
                right=right,
                strike_price=isd["strike"],
            )["Success"][0]
        except requests.exceptions.HttpError as e:
            if e.response.status_code == 503:
                retry = True
        if retry:
            time.sleep(1)
            logging.info("retrying get_quote after 1 s for %s", isd["name"])
            return self._quote(isd)

    def instruments(self, exchange):
        # get instruments file to get tradesymbols
        trading_symbolDict = {}
        f, r = urlretrieve("https://api.kite.trade/instruments")
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

        records = []

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

    def get_quote(self, trading_symbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        isd = get_instrument_data_by_symbol(short_code, trading_symbol)
        bQuote = self._quote(isd)
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.lastTradedPrice = bQuote["ltp"]
        quote.lastTradedQuantity = 0
        quote.avgTradedPrice = 0
        quote.volume = bQuote["total_quantity_traded"]
        quote.totalBuyQuantity = 0
        quote.totalSellQuantity = 0
        quote.open = bQuote["open"]
        quote.high = bQuote["high"]
        quote.low = bQuote["low"]
        quote.close = bQuote["previous_close"]
        quote.change = 0
        quote.oiDayHigh = 0
        quote.oiDayLow = 0
        quote.oi = 0
        quote.lowerCiruitLimit = bQuote["lower_circuit"]
        quote.upperCircuitLimit = bQuote["upper_circuit"]

        return quote

    def get_index_quote(self, trading_symbol, short_code, exchange="NSE"):
        isd = get_instrument_data_by_symbol(short_code, trading_symbol)
        bQuote = self._quote(isd)
        quote = Quote(trading_symbol)
        quote.trading_symbol = trading_symbol
        quote.lastTradedPrice = bQuote["ltp"]
        quote.lastTradedQuantity = 0
        quote.avgTradedPrice = 0
        quote.volume = bQuote["total_quantity_traded"]
        quote.totalBuyQuantity = 0
        quote.totalSellQuantity = 0
        quote.open = bQuote["open"]
        quote.high = bQuote["high"]
        quote.low = bQuote["low"]
        quote.close = bQuote["previous_close"]
        quote.change = 0
        quote.oiDayHigh = 0
        quote.oiDayLow = 0
        quote.oi = 0
        quote.lowerCiruitLimit = bQuote["lower_circuit"]
        quote.upperCircuitLimit = bQuote["upper_circuit"]

        return quote
