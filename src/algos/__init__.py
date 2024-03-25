from algos.baseAlgo import BaseAlgo


class TestAlgo(BaseAlgo):

    def startStrategies(self, short_code, multiple=0):
        # start running strategies: Run each strategy in a separate thread
        # run = [expiry, mon, tue, wed, thru, fri, -4expiry, -3 expiry, -2 expiry, -1 expiry]

        # Test Strategy
        self.startStrategy(ManualStrategy, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        # self.startStrategy( BNSell955CPR602xRe, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        # self.startStrategy( Bankex, short_code, multiple, [1,1,1,1,1,1,1,1,1,1])
        self.startTimedStrategy(MidCpNifty, short_code, multiple, [1, 1, 1, 1, 1, 1, 1, 1, 1, 1], startTimestamp=Utils.getTimeOfToDay(9, 25, 0))
