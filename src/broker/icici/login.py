import logging
import urllib
from typing import Dict

from breeze_connect import BreezeConnect  # type: ignore[import-untyped]

from broker import BaseLogin
from broker.icici import Handler
from config import get_system_config


class ICICILogin(BaseLogin):
    def __init__(self, user_details: Dict[str, str]):
        BaseLogin.__init__(self, user_details)

    def login(self, args):
        logging.info("==> ICICILogin .args => %s", args)
        system_config = get_system_config()
        broker_handle = BreezeConnect(api_key=self.user_details["key"])
        self.set_broker_handler(Handler(broker_handle, self.user_details))
        redirect_url = None
        if "apisession" in args:

            apisession = args["apisession"]

            logging.info("ICICI apisession = %s", apisession)

            self.set_access_token(apisession)

            if not broker_handle.user_id == self.user_details["clientID"]:
                raise Exception("Invalid User Credentials")

            logging.info("ICICI Login successful. apisession = %s", apisession)

            homeUrl = system_config["homeUrl"]
            logging.info("ICICI Redirecting to home page %s", homeUrl)

            redirect_url = homeUrl
        else:
            redirect_url = "https://api.icicidirect.com/apiuser/login?api_key=" + urllib.parse.quote_plus(self.user_details["key"])

        return redirect_url
