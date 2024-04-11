import logging
from typing import Dict

from kiteconnect import KiteConnect  # type: ignore[import-untyped]

from broker import BaseLogin
from broker.zerodha import Handler
from config import get_system_config


class ZerodhaLogin(BaseLogin):
    def __init__(self, user_details: Dict[str, str]):
        super().__init__(user_details)

    def login(self, args):
        logging.info("==> ZerodhaLogin .args => %s", args)
        systemConfig = get_system_config()
        broker_handle = KiteConnect(api_key=self.user_details["key"])
        self.set_broker_handler(Handler(broker_handle, self.user_details))
        redirectUrl = None
        if "request_token" in args:
            requestToken = args["request_token"]
            logging.info("Zerodha requestToken = %s", requestToken)
            broker_session = broker_handle.generate_session(requestToken, api_secret=self.user_details["secret"])

            if not broker_session["user_id"] == self.user_details["clientID"]:
                raise Exception("Invalid User Credentials")

            access_token = broker_session["access_token"]
            logging.info("Zerodha access_token = %s", access_token)
            # set broker handle and access token to the instance
            self.set_access_token(access_token)

            logging.info("Zerodha Login successful. access_token = %s", access_token)

            # redirect to home page with query param loggedIn=true
            homeUrl = systemConfig["homeUrl"] + "?loggedIn=true"
            logging.info("Zerodha Redirecting to home page %s", homeUrl)
            redirectUrl = homeUrl
        else:
            loginUrl = broker_handle.login_url()
            logging.info("Redirecting to zerodha login url = %s", loginUrl)
            redirectUrl = loginUrl

        return redirectUrl
