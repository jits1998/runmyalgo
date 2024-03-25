from time import sleep
from typing import Optional

from broker.base import BaseLogin


class UserDetails:
    def __init__(self) -> None:
        pass

    broker: str
    key: str
    secret: str
    short_code: str
    clientID: str
    algoType: str
    multiple: float
