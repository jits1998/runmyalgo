import datetime
import threading
from json import JSONEncoder
from typing import Union

from algos.base import BaseAlgo
from core.strategy import BaseStrategy, ManualStrategy, TestStrategy


def get_algo(short_code: str) -> Union[BaseAlgo, None]:
    for t in threading.enumerate():
        if t.getName() == short_code:
            assert isinstance(t, BaseAlgo)
            algo: BaseAlgo = t
            return algo
    return None


class TestAlgo(BaseAlgo):

    async def start_strategies(self, short_code, multiple=0):
        # start running strategies: Run each strategy in a separate thread
        # run = [expiry, mon, tue, wed, thru, fri, -4expiry, -3 expiry, -2 expiry, -1 expiry]

        # Test Strategy
        await self.start_strategy(ManualStrategy, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        await self.start_strategy(TestStrategy, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        # self.startStrategy( BNSell955CPR602xRe, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        # self.startStrategy( Bankex, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        # self.startTimedStrategy(MidCpNifty, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], startTimestamp=Utils.getTimeOfToDay(9, 25, 0))
