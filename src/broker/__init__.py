import importlib
import logging
from typing import Any, Dict

from broker.base import BaseHandler, BaseLogin, BaseOrderManager, BaseTicker

brokers: Dict[str, Dict[str, Any]] = {}


def load_broker_module(module_name: str):
    module = importlib.import_module("broker." + module_name)
    logging.info("loaded =>" + str(module))
