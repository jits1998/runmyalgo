import json
import logging
import os
from typing import Dict

from config import getServerConfig
from utils import getBrokerLogin, getEpoch

instrumentsData: Dict[str, Dict] = {}
symbolToInstrumentMap = {}
tokenToInstrumentMap = {}


def getTimestampsData(short_code):
    serverConfig = getServerConfig()
    timestampsFilePath = os.path.join(serverConfig["deployDir"], short_code + "_timestamps.json")
    if os.path.exists(timestampsFilePath) == False:
        return {}
    timestampsFile = open(timestampsFilePath, "r")
    timestamps = json.loads(timestampsFile.read())
    return timestamps


def saveTimestampsData(short_code, timestamps={}):
    serverConfig = getServerConfig()
    timestampsFilePath = os.path.join(serverConfig["deployDir"], short_code + "_timestamps.json")
    with open(timestampsFilePath, "w") as timestampsFile:
        json.dump(timestamps, timestampsFile, indent=2)
    print("saved timestamps data to file " + timestampsFilePath)


def shouldFetchFromServer(short_code):
    timestamps = getTimestampsData(short_code)
    if "instrumentsLastSavedAt" not in timestamps:
        return True
    lastSavedTimestamp = timestamps["instrumentsLastSavedAt"]
    nowEpoch = getEpoch()
    if nowEpoch - lastSavedTimestamp >= 24 * 60 * 60:
        logging.info("Instruments: shouldFetchFromServer() returning True as its been 24 hours since last fetch.")
        return True
    return False


def updateLastSavedTimestamp(short_code):
    timestamps = getTimestampsData(short_code)
    timestamps["instrumentsLastSavedAt"] = getEpoch()
    saveTimestampsData(short_code, timestamps)


def loadInstruments(short_code):
    serverConfig = getServerConfig()
    instrumentsFilepath = os.path.join(serverConfig["deployDir"], short_code + "_instruments.json")
    if os.path.exists(instrumentsFilepath) == False:
        logging.warn("Instruments: instrumentsFilepath %s does not exist", instrumentsFilepath)
        return []  # returns empty list

    isdFile = open(instrumentsFilepath, "r")
    instruments = json.loads(isdFile.read())
    logging.info("Instruments: loaded %d instruments from file %s", len(instruments), instrumentsFilepath)
    return instruments


def saveInstruments(short_code, instruments=[]):
    serverConfig = getServerConfig()
    instrumentsFilepath = os.path.join(serverConfig["deployDir"], short_code + "_instruments.json")
    with open(instrumentsFilepath, "w") as isdFile:
        json.dump(instruments, isdFile, indent=2, default=str)
    logging.info("Instruments: Saved %d instruments to file %s", len(instruments), instrumentsFilepath)
    # Update last save timestamp
    updateLastSavedTimestamp(short_code)


def fetchInstrumentsFromServer(short_code):
    instrumentsList = []
    try:
        brokerHandle = getBrokerLogin(short_code).getBrokerHandle()
        logging.info("Going to fetch instruments from server...")
        instrumentsList = brokerHandle.instruments("NSE")
        instrumentsListFnO = brokerHandle.instruments("NFO")
        intrumentListBSE = brokerHandle.instruments("BSE")
        instrumentsListBFO = brokerHandle.instruments("BFO")
        # Add FnO instrument list to the main list
        instrumentsList.extend(instrumentsListFnO)
        instrumentsList.extend(intrumentListBSE)
        instrumentsList.extend(instrumentsListBFO)
        logging.info("Fetched %d instruments from server.", len(instrumentsList))
    except Exception as e:
        logging.exception("Exception while fetching instruments from server")
        return []
    return instrumentsList


def fetchInstruments(short_code):
    global instrumentsData
    if short_code in instrumentsData:
        return instrumentsData[short_code]

    instrumentsList = loadInstruments(short_code)
    if len(instrumentsList) == 0 or shouldFetchFromServer(short_code) == True:
        instrumentsList = fetchInstrumentsFromServer(short_code)
        # Save instruments to file locally
        if len(instrumentsList) > 0:
            saveInstruments(short_code, instrumentsList)

    if len(instrumentsList) == 0:
        print("Could not fetch/load instruments data. Hence exiting the app.")
        logging.error("Could not fetch/load instruments data. Hence exiting the app.")
        return instrumentsList

    symbolToInstrumentMap[short_code] = {}
    tokenToInstrumentMap[short_code] = {}
    getBrokerLogin(short_code).getBrokerHandle().instruments = instrumentsList

    try:
        for isd in instrumentsList:
            tradingSymbol = isd["tradingsymbol"]
            instrumentToken = isd["instrument_token"]
            # logging.info('%s = %d', tradingSymbol, instrumentToken)
            symbolToInstrumentMap[short_code][tradingSymbol] = isd
            tokenToInstrumentMap[short_code][instrumentToken] = isd
    except Exception as e:
        logging.exception("Exception while fetching instruments from server: %s", str(e))

    logging.info("Fetching instruments done. Instruments count = %d", len(instrumentsList))
    instrumentsData[short_code] = instrumentsList  # assign the list to static variable
    return instrumentsList


def getInstrumentDataBySymbol(short_code, tradingSymbol):
    return symbolToInstrumentMap[short_code][tradingSymbol]


def getInstrumentDataByToken(short_code, instrumentToken):
    return tokenToInstrumentMap[short_code][instrumentToken]
