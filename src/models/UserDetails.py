from threading import Thread
from time import sleep


class UserDetails(Thread):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None):
        super(UserDetails, self).__init__(group=group, target=target, name=name)
        (self.broker,) = args
        self.key = None
        self.secret = None
        self.short_code = None
        self.loginHandler = None
        self.tradeManager = None

    def run(self):
        while True:
            sleep(10)

    def getName(self) -> str:
        return self.short_code
