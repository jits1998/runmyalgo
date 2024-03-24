import threading


def getTradeManager(short_code):
    for t in threading.enumerate():
        if t.getName() == short_code:
            return t.tradeManager
    return None
