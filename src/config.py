import functools
import json
from typing import Dict

import app


def get_server_config() -> Dict[str, str]:
    return app.server_config


def get_system_config() -> Dict[str, str]:
    return app.system_config


def get_user_config(short_code: str) -> Dict[str, str]:
    with open("../user_config/{short_code}.json".format(short_code=short_code), "r") as brokerapp:
        user_data = json.load(brokerapp)
        return user_data


@functools.lru_cache
def get_holidays() -> list:
    with open("../user_config/holidays.list", "r") as holidays_file:
        holidays = holidays_file.read().splitlines()
        return holidays
