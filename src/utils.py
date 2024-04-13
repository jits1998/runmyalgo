import asyncio
import calendar
import functools
import logging
import time
from datetime import datetime, timedelta

from config import get_holidays, get_user_config
from models import Direction, TradeState, UserDetails
from models.trade import Trade

DateFormat = "%Y-%m-%d"
timeFormat = "%H:%M:%S"
dateTimeFormat = "%Y-%m-%d %H:%M:%S"


@functools.lru_cache
def get_user_details(short_code: str) -> UserDetails:
    user_config: dict = get_user_config(short_code)

    user_details = UserDetails()
    user_details.short_code = short_code
    user_details.broker_name = user_config["broker"]
    user_details.client_id = user_config["clientID"]
    user_details.secret = user_config["appSecret"]
    user_details.key = user_config["appKey"]
    user_details.multiple = int(user_config["multiple"])
    user_details.algo_type = user_config["algo_type"]

    return user_details


def roundoff(price: float) -> float:  # Round off to 2 decimal places
    return round(price, 2)


def calculate_trade_pnl(trade: Trade) -> None:
    if trade.tradeState == TradeState.ACTIVE:
        if trade.cmp > 0:
            if trade.direction == Direction.LONG:
                trade.pnl = roundoff(trade.filled_qty * (trade.cmp - trade.entry))
            else:
                trade.pnl = roundoff(trade.filled_qty * (trade.entry - trade.cmp))
    else:
        if trade.exit > 0:
            if trade.direction == Direction.LONG:
                trade.pnl = roundoff(trade.filled_qty * (trade.exit - trade.entry))
            else:
                trade.pnl = roundoff(trade.filled_qty * (trade.entry - trade.exit))
    tradeValue = trade.entry * trade.filled_qty
    if tradeValue > 0:
        trade.pnlPercentage = roundoff(trade.pnl * 100 / tradeValue)


def get_epoch(datetimeObj=None) -> int:
    # This method converts given datetimeObj to epoch seconds
    if datetimeObj == None:
        datetimeObj = datetime.now()
    epochSeconds = datetime.timestamp(datetimeObj)
    return int(epochSeconds)  # converting double to long


def get_today_date_str() -> str:
    return datetime.now().strftime(DateFormat)


def wait_till_market_open(context) -> None:
    nowEpoch = get_epoch(datetime.now())
    marketStartTimeEpoch = get_epoch(get_market_starttime())
    waitSeconds = marketStartTimeEpoch - nowEpoch
    if waitSeconds > 0:
        logging.info("%s: Waiting for %d seconds till market opens...", context, waitSeconds)
        time.sleep(waitSeconds)


async def wait_till_market_open_async(context) -> None:
    nowEpoch = get_epoch(datetime.now())
    marketStartTimeEpoch = get_epoch(get_market_starttime())
    waitSeconds = marketStartTimeEpoch - nowEpoch
    if waitSeconds > 0:
        logging.info("%s: Waiting for %d seconds till market opens...", context, waitSeconds)
        await asyncio.sleep(waitSeconds)


def get_market_starttime(dateTimeObj=None):
    return get_time(9, 15, 0, dateTimeObj)


def get_market_endtime(dateTimeObj=None):
    return get_time(15, 30, 0, dateTimeObj)


def get_time(hours, minutes, seconds, dateTimeObj=None):
    if dateTimeObj == None:
        dateTimeObj = datetime.now()
    dateTimeObj = dateTimeObj.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
    return dateTimeObj


def prepare_weekly_options_symbol(inputSymbol, strike, optionType, numWeeksPlus=0, expiryDay=2):
    expiryDateTime = get_weekly_expiry_day(inputSymbol, expiryDay=expiryDay)
    # Check if monthly and weekly expiry same
    expiryDateTimeMonthly = get_monthly_expiry_day(expiryDay=expiryDay)
    weekAndMonthExpriySame = False
    if expiryDateTime == expiryDateTimeMonthly or expiryDateTimeMonthly == get_time(0, 0, 0, datetime.now()):
        expiryDateTime = expiryDateTimeMonthly
        weekAndMonthExpriySame = True
        logging.debug("Weekly and Monthly expiry is same for %s", expiryDateTime)

    todayMarketStartTime = get_market_starttime()
    expiryDayMarketEndTime = get_market_endtime(expiryDateTime)
    if numWeeksPlus > 0:
        expiryDateTime = expiryDateTime + timedelta(days=numWeeksPlus * 7)
        expiryDateTime = get_weekly_expiry_day(inputSymbol, expiryDateTime, expiryDay)
    if todayMarketStartTime > expiryDayMarketEndTime:
        expiryDateTime = expiryDateTime + timedelta(days=6)
        expiryDateTime = get_weekly_expiry_day(inputSymbol, expiryDateTime, expiryDay)

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


def get_weekly_expiry_day(inputSymbol, dateTimeObj=None, expiryDay=2):

    expiryDateTimeMonthly = get_monthly_expiry_day(expiryDay=expiryDay)

    if dateTimeObj == None:
        dateTimeObj = datetime.now()

    if expiryDateTimeMonthly == get_time(0, 0, 0, dateTimeObj):
        datetimeExpiryDay = expiryDateTimeMonthly
    else:

        daysToAdd = 0
        if dateTimeObj.weekday() > expiryDay:
            daysToAdd = 7 - (dateTimeObj.weekday() - expiryDay)
        else:
            daysToAdd = expiryDay - dateTimeObj.weekday()
        datetimeExpiryDay = dateTimeObj + timedelta(days=daysToAdd)
        while is_holiday(datetimeExpiryDay) == True:
            datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)

        datetimeExpiryDay = get_time(0, 0, 0, datetimeExpiryDay)

    return datetimeExpiryDay


def get_monthly_expiry_day(datetimeObj=None, expiryDay=3):
    if datetimeObj == None:
        datetimeObj = datetime.now()
    year = datetimeObj.year
    month = datetimeObj.month
    lastDay = calendar.monthrange(year, month)[1]  # 2nd entry is the last day of the month
    datetimeExpiryDay = datetime(year, month, lastDay)
    while datetimeExpiryDay.weekday() != expiryDay:
        datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)
    while is_holiday(datetimeExpiryDay) == True:
        datetimeExpiryDay = datetimeExpiryDay - timedelta(days=1)

    datetimeExpiryDay = get_time(0, 0, 0, datetimeExpiryDay)
    return datetimeExpiryDay


def is_today_weekly_expiry(inputSymbol, expiryDay=2):
    expiryDate = get_weekly_expiry_day(inputSymbol, expiryDay=expiryDay)
    todayDate = get_time_today(0, 0, 0)
    if expiryDate == todayDate:
        return True
    return False


def find_days_before_weekly_expiry(inputSymbol, expiryDay=2):

    if is_today_weekly_expiry(inputSymbol, expiryDay=expiryDay):
        return 0

    expiryDate = get_weekly_expiry_day(inputSymbol, expiryDay=expiryDay)
    dateTimeObj = get_time_today(0, 0, 0)
    currentWeekTradingDates = []

    while dateTimeObj < expiryDate:

        if is_holiday(dateTimeObj):
            dateTimeObj += timedelta(days=1)
            continue

        currentWeekTradingDates.append(dateTimeObj)
        dateTimeObj += timedelta(days=1)
    return len(currentWeekTradingDates)


def get_time_today(hours, minutes, seconds):
    return get_time(hours, minutes, seconds, datetime.now())


def is_holiday(datetimeObj):
    dayOfWeek = calendar.day_name[datetimeObj.weekday()]
    if dayOfWeek == "Saturday" or dayOfWeek == "Sunday":
        return True

    dateStr = datetimeObj.strftime(DateFormat)
    holidays = get_holidays()
    if dateStr in holidays:
        return True
    else:
        return False


def is_today_holiday():
    return is_holiday(datetime.now())


def is_market_closed_for_the_day():
    # This method returns true if the current time is > marketEndTime
    # Please note this will not return true if current time is < marketStartTime on a trading day
    if is_today_holiday():
        return True
    now = datetime.now()
    marketEndTime = get_market_endtime()
    return now > marketEndTime


def prepareMonthlyExpiryFuturesSymbol(inputSymbol, expiryDay=2):
    expiryDateTime = get_monthly_expiry_day(expiryDay=expiryDay)
    expiryDateMarketEndTime = get_market_endtime(expiryDateTime)
    now = datetime.now()
    if now > expiryDateMarketEndTime:
        # increasing today date by 20 days to get some day in next month passing to getMonthlyExpiryDayDate()
        expiryDateTime = get_monthly_expiry_day(now + timedelta(days=20), expiryDay)
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
