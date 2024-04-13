import importlib
import logging
from typing import Dict, Type

from broker.base import Broker, Ticker

brokers: Dict[str, Type[Broker]] = {}
tickers: Dict[str, Type[Ticker]] = {}


def load_broker_module(module_name: str):
    module = importlib.import_module("broker." + module_name)
    logging.info("loaded =>" + str(module))
