import json
import logging
import math
import os
from typing import Dict

from broker.base import Broker
from config import get_server_config
from utils import get_epoch

instruments_data: Dict[str, Dict] = {}
symbol_to_instrument: Dict[str, Dict[str, str]] = {}
token_to_instrument: Dict[str, Dict[str, str]] = {}
symbol_to_CMP: Dict[str, Dict[str, float]] = {}


def get_cmp(short_code, trading_symbol) -> float:
    return symbol_to_CMP[short_code][trading_symbol]


def get_timestamps(short_code):
    server_config = get_server_config()
    timestamps_filepath = os.path.join(server_config["deploy_dir"], short_code + "_timestamps.json")
    if os.path.exists(timestamps_filepath) == False:
        return {}
    with open(timestamps_filepath, "r") as timestamps_file:
        timestamps = json.loads(timestamps_file.read())
    return timestamps


def save_timestamps(short_code, timestamps={}):
    server_config = get_server_config()
    timestamps_filepath = os.path.join(server_config["deploy_dir"], short_code + "_timestamps.json")
    with open(timestamps_filepath, "w") as timestamps_file:
        json.dump(timestamps, timestamps_file, indent=2)
    print("saved timestamps data to file " + timestamps_filepath)


def should_fetch_from_server(short_code):
    timestamps = get_timestamps(short_code)
    if "instruments_last_saved_at" not in timestamps:
        return True
    last_saved = timestamps["instruments_last_saved_at"]
    now_epoch = get_epoch()
    if now_epoch - last_saved >= 24 * 60 * 60:
        logging.info("Instruments: shouldFetchFromServer() returning True as its been 24 hours since last fetch.")
        return True
    return False


def update_last_saved(short_code):
    timestamps = get_timestamps(short_code)
    timestamps["instruments_last_saved_at"] = get_epoch()
    save_timestamps(short_code, timestamps)


def load_instruments(short_code):
    server_config = get_server_config()
    instruments_filepath = os.path.join(server_config["deploy_dir"], short_code + "_instruments.json")
    if os.path.exists(instruments_filepath) == False:
        logging.warn("Instruments: instrumentsFilepath %s does not exist", instruments_filepath)
        return []  # returns empty list

    isdFile = open(instruments_filepath, "r")
    instruments = json.loads(isdFile.read())
    logging.info("Instruments: loaded %d instruments from file %s", len(instruments), instruments_filepath)
    return instruments


def save_instruments(short_code, instruments=[]):
    server_config = get_server_config()
    instruments_filepath = os.path.join(server_config["deploy_dir"], short_code + "_instruments.json")
    with open(instruments_filepath, "w") as isdFile:
        json.dump(instruments, isdFile, indent=2, default=str)
    logging.info("Instruments: Saved %d instruments to file %s", len(instruments), instruments_filepath)
    # Update last save timestamp
    update_last_saved(short_code)


def fetch_instruments_from_server(short_code, broker: Broker):
    instruments_list = []
    try:
        logging.info("Going to fetch instruments from server...")
        instruments_list = broker.instruments("NSE")
        fno_instruments = broker.instruments("NFO")
        bse_intruments = broker.instruments("BSE")
        bfo_instruments = broker.instruments("BFO")
        # Add FnO instrument list to the main list
        instruments_list.extend(fno_instruments)
        instruments_list.extend(bse_intruments)
        instruments_list.extend(bfo_instruments)
        logging.info("Fetched %d instruments from server.", len(instruments_list))
    except Exception as e:
        logging.exception("Exception while fetching instruments from server")
        return []
    return instruments_list


def fetch_instruments(short_code, broker: Broker):
    symbol_to_CMP[short_code] = {}
    if short_code in instruments_data:
        return instruments_data[short_code]

    instruments_list = load_instruments(short_code)
    if len(instruments_list) == 0 or should_fetch_from_server(short_code) == True:
        instruments_list = fetch_instruments_from_server(short_code, broker)
        # Save instruments to file locally
        if len(instruments_list) > 0:
            save_instruments(short_code, instruments_list)

    if len(instruments_list) == 0:
        print("Could not fetch/load instruments data. Hence exiting the app.")
        logging.error("Could not fetch/load instruments data. Hence exiting the app.")
        return instruments_list

    symbol_to_instrument[short_code] = {}
    token_to_instrument[short_code] = {}
    broker.instruments_list = instruments_list

    try:
        for isd in instruments_list:
            trading_symbol = isd["tradingsymbol"]
            instrument_token = isd["instrument_token"]
            # logging.info('%s = %d', trading_symbol, instrumentToken)
            symbol_to_instrument[short_code][trading_symbol] = isd
            token_to_instrument[short_code][instrument_token] = isd
    except Exception as e:
        logging.exception("Exception while fetching instruments from server: %s", str(e))

    logging.info("Fetching instruments done. Instruments count = %d", len(instruments_list))
    instruments_data[short_code] = instruments_list  # assign the list to static variable
    return instruments_list


def get_instrument_data_by_symbol(short_code, trading_symbol):
    return symbol_to_instrument[short_code][trading_symbol]


def get_instrument_data_by_token(short_code, instrument_token):
    return token_to_instrument[short_code][instrument_token]


def round_to_ticksize(short_code: str, trading_symbol: str, price: float) -> float:
    tick_size: float = get_instrument_data_by_symbol(short_code, trading_symbol)["tick_size"]
    return max(round(tick_size * math.ceil(price / tick_size), 2), 0.05) if price != 0 else 0
