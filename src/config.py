import functools
import json

import app


def getServerConfig():
    return app.serverConfig


def getSystemConfig():
    return app.systemConfig


@functools.lru_cache
def getUserConfig(short_code):
    with open("./user_config/{short_code}.json".format(short_code=short_code), "r") as brokerapp:
        jsonUserData = json.load(brokerapp)
        return jsonUserData


@functools.lru_cache
def getHolidays():
    with open("./user_config/holidays.list", "r") as holidays:
        holidaysData = holidays.read().splitlines()
        return holidaysData
