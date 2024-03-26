import csv
import datetime
from io import BytesIO, TextIOWrapper
from urllib.request import urlopen, urlretrieve
from zipfile import ZipFile

import dateutil.parser
from breeze_connect import config as breeze_config  # type: ignore[import-untyped]

from broker import BaseHandler
from core import Quote
from models import OrderStatus


class ICICIHandler(BaseHandler):

    def __init__(self, brokerHandle, config):
        super().__init__(brokerHandle)
        self.brokerHandle = brokerHandle
        self.config = config

    def set_access_token(self, access_token):
        self.brokerHandle.generate_session(session_token=access_token, api_secret=self.config["secret"])

    def margins(self):
        margins = self.brokerHandle.get_margin(exchange_code="NFO")

        return margins

    def positions(self):
        raise Exception("Method not to be called")

    def orders(self):
        order_list = self.brokerHandle.get_order_list(
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

    def quote(self, isd):
        product_type = ""
        right = ""
        if isd["instrument_type"] == "PE":
            product_type = "options"
            right = "PUT"
        elif isd["instrument_type"] == "CE":
            product_type = "options"
            right = "CALL"
        elif isd["expiry"] != "":
            product_type = "futures"
            right = "Others"

        return self.brokerHandle.get_quotes(
            stock_code=isd["name"],
            exchange_code=isd["exchange"],
            expiry_date=isd["expiry"],
            product_type=product_type,
            right=right,
            strike_price=isd["strike"],
        )["Success"][0]

    def instruments(self, exchange):
        # get instruments file to get tradesymbols
        tradingSymbolDict = {}
        f, r = urlretrieve("https://api.kite.trade/instruments")
        with open(f, newline="") as csvfile:
            r = csv.DictReader(csvfile)
            for row in r:
                tradingSymbolDict[row["exchange_token"]] = row["tradingsymbol"]

        resp = urlopen(breeze_config.SECURITY_MASTER_URL)
        zipfile = ZipFile(BytesIO(resp.read()))
        mapper_exchangecode_to_file = breeze_config.ISEC_NSE_CODE_MAP_FILE

        if exchange == "NFO":
            exchange = "fonse"

        file_key = mapper_exchangecode_to_file.get(exchange.lower())
        if file_key is None:
            return []
        required_file = zipfile.open(file_key)

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
        records = []

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
                instrument["tradingsymbol"] = tradingSymbolDict.get(instrument["exchange_token"], None)
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

    def getQuote(self, tradingSymbol: str, short_code: str, isFnO: bool, exchange: str) -> Quote:
        raise Exception("Method not to be called")
