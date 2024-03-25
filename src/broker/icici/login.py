import logging
import urllib
from typing import Dict

from breeze_connect import BreezeConnect  # type: ignore[import-untyped]

from broker import BaseLogin
from broker.icici import ICICIHandler
from config import getSystemConfig


class ICICILogin(BaseLogin):
    def __init__(self, userDetails: Dict[str, str]):
        BaseLogin.__init__(self, userDetails)

    def login(self, args):
        logging.info("==> ICICILogin .args => %s", args)
        systemConfig = getSystemConfig()
        brokerHandle = BreezeConnect(api_key=self.userDetails["key"])
        self.setBrokerHandler(ICICIHandler(brokerHandle, self.userDetails))
        redirectUrl = None
        if "apisession" in args:

            apisession = args["apisession"]

            logging.info("ICICI apisession = %s", apisession)

            self.setAccessToken(apisession)

            if not brokerHandle.user_id == self.userDetails["clientID"]:
                raise Exception("Invalid User Credentials")

            logging.info("ICICI Login successful. apisession = %s", apisession)

            homeUrl = systemConfig["homeUrl"]
            logging.info("ICICI Redirecting to home page %s", homeUrl)

            redirectUrl = homeUrl
        else:
            redirectUrl = "https://api.icicidirect.com/apiuser/login?api_key=" + urllib.parse.quote_plus(self.userDetails["key"])

        return redirectUrl
