import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Union

from config import getUserConfig
from models import UserDetails

DateFormat = "%Y-%m-%d"
timeFormat = "%H:%M:%S"
dateTimeFormat = "%Y-%m-%d %H:%M:%S"


def getUserDetails(short_code: str) -> UserDetails:
    userConfig: dict = getUserConfig(short_code)

    userDetails = UserDetails()
    userDetails.short_code = short_code
    userDetails.broker = userConfig["broker"]
    userDetails.clientID = userConfig["clientID"]
    userDetails.secret = userConfig["appSecret"]
    userDetails.key = userConfig["appKey"]
    userDetails.multiple = userConfig["multiple"]
    userDetails.algoType = userConfig["algoType"]

    return userDetails


def getEpoch(datetimeObj=None):
    # This method converts given datetimeObj to epoch seconds
    if datetimeObj == None:
        datetimeObj = datetime.now()
    epochSeconds = datetime.timestamp(datetimeObj)
    return int(epochSeconds)  # converting double to long


def getTodayDateStr() -> str:
    return datetime.now().strftime(DateFormat)


def waitTillMarketOpens(context) -> None:
    nowEpoch = getEpoch(datetime.now())
    marketStartTimeEpoch = getEpoch(getMarketStartTime())
    waitSeconds = marketStartTimeEpoch - nowEpoch
    if waitSeconds > 0:
        logging.info("%s: Waiting for %d seconds till market opens...", context, waitSeconds)
        time.sleep(waitSeconds)


def getMarketStartTime(dateTimeObj=None):
    return getTimeOfDay(9, 15, 0, dateTimeObj)


def getTimeOfDay(hours, minutes, seconds, dateTimeObj=None):
    if dateTimeObj == None:
        dateTimeObj = datetime.now()
    dateTimeObj = dateTimeObj.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
    return dateTimeObj
