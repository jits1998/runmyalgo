import calendar
import logging
import time
from datetime import datetime, timedelta

from config import getHolidays, getUserConfig
from models import Direction, TradeState, UserDetails

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


def roundOff(price):  # Round off to 2 decimal places
    return round(price, 2)


def calculateTradePnl(trade):
    if trade.tradeState == TradeState.ACTIVE:
        if trade.cmp > 0:
            if trade.direction == Direction.LONG:
                trade.pnl = roundOff(trade.filledQty * (trade.cmp - trade.entry))
            else:
                trade.pnl = roundOff(trade.filledQty * (trade.entry - trade.cmp))
    else:
        if trade.exit > 0:
            if trade.direction == Direction.LONG:
                trade.pnl = roundOff(trade.filledQty * (trade.exit - trade.entry))
            else:
                trade.pnl = roundOff(trade.filledQty * (trade.entry - trade.exit))
    tradeValue = trade.entry * trade.filledQty
    if tradeValue > 0:
        trade.pnlPercentage = roundOff(trade.pnl * 100 / tradeValue)

    return trade


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


def getMarketEndTime(dateTimeObj=None):
    return getTimeOfDay(15, 30, 0, dateTimeObj)


def getTimeOfDay(hours, minutes, seconds, dateTimeObj=None):
    if dateTimeObj == None:
        dateTimeObj = datetime.now()
    dateTimeObj = dateTimeObj.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
    return dateTimeObj


def prepareWeeklyOptionsSymbol(inputSymbol, strike, optionType, numWeeksPlus=0, expiryDay=2):
    expiryDateTime = getWeeklyExpiryDayDate(inputSymbol, expiryDay=expiryDay)
    # Check if monthly and weekly expiry same
    expiryDateTimeMonthly = getMonthlyExpiryDayDate(expiryDay=expiryDay)
    weekAndMonthExpriySame = False
    if expiryDateTime == expiryDateTimeMonthly or expiryDateTimeMonthly == getTimeOfDay(0, 0, 0, datetime.now()):
        expiryDateTime = expiryDateTimeMonthly
        weekAndMonthExpriySame = True
        logging.debug("Weekly and Monthly expiry is same for %s", expiryDateTime)

    todayMarketStartTime = getMarketStartTime()
    expiryDayMarketEndTime = getMarketEndTime(expiryDateTime)
    if numWeeksPlus > 0:
        expiryDateTime = expiryDateTime + timedelta(days=numWeeksPlus * 7)
        expiryDateTime = getWeeklyExpiryDayDate(inputSymbol, expiryDateTime, expiryDay)
    if todayMarketStartTime > expiryDayMarketEndTime:
        expiryDateTime = expiryDateTime + timedelta(days=6)
        expiryDateTime = getWeeklyExpiryDayDate(inputSymbol, expiryDateTime, expiryDay)

    year2Digits = str(expiryDateTime.year)[2:]
    optionSymbol = None
    if weekAndMonthExpriySame == True:
        monthShort = calendar.month_name[expiryDateTime.month].upper()[0:3]
        optionSymbol = inputSymbol + str(year2Digits) + monthShort + str(strike) + optionType.upper()
    else:
        m = expiryDateTime.month
        d = expiryDateTime.day
        mStr = str(m)
        if m == 10:
            mStr = "O"
        elif m == 11:
            mStr = "N"
        elif m == 12:
            mStr = "D"
        dStr = ("0" + str(d)) if d < 10 else str(d)
        optionSymbol = inputSymbol + str(year2Digits) + mStr + dStr + str(strike) + optionType.upper()
    # logging.info('prepareWeeklyOptionsSymbol[%s, %d, %s, %d] = %s', inputSymbol, strike, optionType, numWeeksPlus, optionSymbol)
    return optionSymbol


def getWeeklyExpiryDayDate(inputSymbol, dateTimeObj=None, expiryDay=2):

    expiryDateTimeMonthly = getMonthlyExpiryDayDate(expiryDay=expiryDay)

    if dateTimeObj == None:
        dateTimeObj = datetime.now()

    if expiryDateTimeMonthly == getTimeOfDay(0, 0, 0, dateTimeObj):
        datetimeExpiryDay = expiryDateTimeMonthly
    else:

        daysToAdd = 0
        if dateTimeObj.weekday() > expiryDay:
            daysToAdd = 7 - (dateTimeObj.weekday() - expiryDay)
        else:
            daysToAdd = expiryDay - dateTimeObj.weekday()
        datetimeExpiryDay = dateTimeObj + timedelta(days=daysToAdd)
        while isHoliday(datetimeExpiryDay) == True:
            datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)

        datetimeExpiryDay = getTimeOfDay(0, 0, 0, datetimeExpiryDay)

    return datetimeExpiryDay


def getMonthlyExpiryDayDate(datetimeObj=None, expiryDay=3):
    if datetimeObj == None:
        datetimeObj = datetime.now()
    year = datetimeObj.year
    month = datetimeObj.month
    lastDay = calendar.monthrange(year, month)[1]  # 2nd entry is the last day of the month
    datetimeExpiryDay = datetime(year, month, lastDay)
    while datetimeExpiryDay.weekday() != expiryDay:
        datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)
    while isHoliday(datetimeExpiryDay) == True:
        datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)

    datetimeExpiryDay = getTimeOfDay(0, 0, 0, datetimeExpiryDay)
    return datetimeExpiryDay


def isTodayWeeklyExpiryDay(inputSymbol, expiryDay=2):
    expiryDate = getWeeklyExpiryDayDate(inputSymbol, expiryDay=expiryDay)
    todayDate = getTimeOfToDay(0, 0, 0)
    if expiryDate == todayDate:
        return True
    return False


def findNumberOfDaysBeforeWeeklyExpiryDay(inputSymbol, expiryDay=2):

    if isTodayWeeklyExpiryDay(inputSymbol, expiryDay=expiryDay):
        return 0

    expiryDate = getWeeklyExpiryDayDate(inputSymbol, expiryDay=expiryDay)
    dateTimeObj = getTimeOfToDay(0, 0, 0)
    currentWeekTradingDates = []

    while dateTimeObj < expiryDate:

        if isHoliday(dateTimeObj):
            dateTimeObj += timedelta(days=1)
            continue

        currentWeekTradingDates.append(dateTimeObj)
        dateTimeObj += timedelta(days=1)
    return len(currentWeekTradingDates)


def getTimeOfToDay(hours, minutes, seconds):
    return getTimeOfDay(hours, minutes, seconds, datetime.now())


def isHoliday(datetimeObj):
    dayOfWeek = calendar.day_name[datetimeObj.weekday()]
    if dayOfWeek == "Saturday" or dayOfWeek == "Sunday":
        return True

    dateStr = datetimeObj.strftime(DateFormat)
    holidays = getHolidays()
    if dateStr in holidays:
        return True
    else:
        return False


def isTodayHoliday():
    return isHoliday(datetime.now())


def isMarketClosedForTheDay():
    # This method returns true if the current time is > marketEndTime
    # Please note this will not return true if current time is < marketStartTime on a trading day
    if isTodayHoliday():
        return True
    now = datetime.now()
    marketEndTime = getMarketEndTime()
    return now > marketEndTime


def prepareMonthlyExpiryFuturesSymbol(inputSymbol, expiryDay=2):
    expiryDateTime = getMonthlyExpiryDayDate(expiryDay=expiryDay)
    expiryDateMarketEndTime = getMarketEndTime(expiryDateTime)
    now = datetime.now()
    if now > expiryDateMarketEndTime:
        # increasing today date by 20 days to get some day in next month passing to getMonthlyExpiryDayDate()
        expiryDateTime = getMonthlyExpiryDayDate(now + timedelta(days=20), expiryDay)
    year2Digits = str(expiryDateTime.year)[2:]
    monthShort = calendar.month_name[expiryDateTime.month].upper()[0:3]
    futureSymbol = inputSymbol + year2Digits + monthShort + "FUT"
    logging.info("prepareMonthlyExpiryFuturesSymbol[%s] = %s", inputSymbol, futureSymbol)
    return futureSymbol


def getNearestStrikePrice(price, nearestMultiple=50):
    inputPrice = int(price)
    remainder = int(inputPrice % nearestMultiple)
    if remainder < int(nearestMultiple / 2):
        return inputPrice - remainder
    else:
        return inputPrice + (nearestMultiple - remainder)
