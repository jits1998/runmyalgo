import threading
from typing import Union

from algos.baseAlgo import BaseAlgo
from core.strategy import ManualStrategy, TestStrategy


def getAlgo(short_code: str) -> Union[BaseAlgo, None]:
    for t in threading.enumerate():
        if t.getName() == short_code:
            assert isinstance(t, BaseAlgo)
            algo: BaseAlgo = t
            return algo
    return None


class TestAlgo(BaseAlgo):

    async def startStrategies(self, short_code, multiple=0):
        # start running strategies: Run each strategy in a separate thread
        # run = [expiry, mon, tue, wed, thru, fri, -4expiry, -3 expiry, -2 expiry, -1 expiry]

        # Test Strategy
        await self.startStrategy(ManualStrategy, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        await self.startStrategy(TestStrategy, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        # self.startStrategy( BNSell955CPR602xRe, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        # self.startStrategy( Bankex, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        # self.startTimedStrategy(MidCpNifty, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], startTimestamp=Utils.getTimeOfToDay(9, 25, 0))
