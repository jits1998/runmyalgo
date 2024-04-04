import logging
from typing import Dict

from kiteconnect import KiteConnect  # type: ignore[import-untyped]

from broker import BaseLogin
from broker.zerodha import Handler
from config import getSystemConfig


class ZerodhaLogin(BaseLogin):
    def __init__(self, userDetails: Dict[str, str]):
        super().__init__(userDetails)

    def login(self, args):
        logging.info("==> ZerodhaLogin .args => %s", args)
        systemConfig = getSystemConfig()
        brokerHandle = KiteConnect(api_key=self.userDetails["key"])
        self.setBrokerHandler(Handler(brokerHandle, self.userDetails))
        redirectUrl = None
        if "request_token" in args:
            requestToken = args["request_token"]
            logging.info("Zerodha requestToken = %s", requestToken)
            broker_session = brokerHandle.generate_session(requestToken, api_secret=self.userDetails["secret"])

            if not broker_session["user_id"] == self.userDetails["clientID"]:
                raise Exception("Invalid User Credentials")

            accessToken = broker_session["access_token"]
            logging.info("Zerodha accessToken = %s", accessToken)
            # set broker handle and access token to the instance
            self.setAccessToken(accessToken)

            logging.info("Zerodha Login successful. accessToken = %s", accessToken)

            # redirect to home page with query param loggedIn=true
            homeUrl = systemConfig["homeUrl"] + "?loggedIn=true"
            logging.info("Zerodha Redirecting to home page %s", homeUrl)
            redirectUrl = homeUrl
        else:
            loginUrl = brokerHandle.login_url()
            logging.info("Redirecting to zerodha login url = %s", loginUrl)
            redirectUrl = loginUrl

        return redirectUrl
