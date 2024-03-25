from typing import Any, Dict


class TradeManager:

    strategyToInstanceMap: Dict[str, Any] = {}
    symbolToCMPMap: Dict[str, float] = {}

    def __init__(self, short_code: str) -> None:
        self.short_code: str = short_code
