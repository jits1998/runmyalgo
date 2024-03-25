import functools
import json
from typing import Dict

import app


def getServerConfig() -> Dict[str, str]:
    return app.serverConfig


def getSystemConfig() -> Dict[str, str]:
    return app.systemConfig


@functools.lru_cache
def getUserConfig(short_code: str) -> Dict[str, str]:
    with open("../user_config/{short_code}.json".format(short_code=short_code), "r") as brokerapp:
        jsonUserData = json.load(brokerapp)
        return jsonUserData


@functools.lru_cache
def getHolidays() -> list:
    with open("../user_config/holidays.list", "r") as holidays:
        holidaysData = holidays.read().splitlines()
        return holidaysData
