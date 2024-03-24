import importlib

brokers = {}


def load_broker_module(module_name):
    module = importlib.import_module("broker." + module_name)
    print("loaded =>" + str(module))
