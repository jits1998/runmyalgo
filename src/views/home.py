import importlib
import json
import logging
import time
from functools import wraps
from typing import Callable

from flask import abort, redirect, render_template, request, session

from algos import BaseAlgo, get_algo
from app import flask_app as app
from app import system_config
from broker import brokers, load_broker_module
from broker.base import Broker
from instruments import symbol_to_CMP
from models import AlgoStatus
from utils import get_user_details


@app.route("/me/<short_code>")
def home(short_code):
    if session.get("short_code", None) is not None and not short_code == session["short_code"]:
        session.clear()

    session["short_code"] = short_code
    algo = get_algo(short_code)
    user_details = get_user_details(short_code)

    # special case of server restart and access_token provided via query params
    if request.args.get("access_token", None) is not None:
        session["access_token"] = request.args["access_token"]

    if session.get("access_token", None) is None:
        return render_template("index.html", broker=user_details.broker_name)  # take the user to login
    else:
        # access code is available in session
        broker = None
        if algo is None:
            # lets prepare for starting algo
            algo = _initiate_algo(user_details)
        elif algo.status == AlgoStatus.STARTED:
            broker = algo.broker

        return render_template(
            "main.html",
            strategies=algo.strategy_to_instance.values(),
            ltps=symbol_to_CMP[short_code] if short_code in symbol_to_CMP else {},
            algoStarted=True if broker is not None else False,
            isReady=True if broker is not None else False,
            # margins=(broker.margins() if broker is not None else {}),
            positions={},  # (broker.positions() if broker is not None else {}),
            orders={},  # (broker.orders() if broker is not None else {}),
            multiple=user_details.multiple,
            short_code=short_code,
        )


@app.route("/apis/broker/login/<broker_name>", methods=["GET", "POST"])
def login(broker_name: str):

    load_broker_module(broker_name)

    short_code: str = session["short_code"]
    user_details = get_user_details(short_code)
    broker: Broker = brokers[broker_name](user_details.__dict__)
    redirectUrl: str = broker.login(request.args)

    if broker.get_access_token() is not None:
        session["access_token"] = broker.access_token
        algo = _initiate_algo(user_details)
        algo.broker = broker

    return redirect(redirectUrl, code=302)


def _initiate_algo(user_details) -> BaseAlgo:
    algo_type = user_details.algo_type
    algoConfigModule = importlib.import_module("algos")
    algoConfigClass = getattr(algoConfigModule, algo_type)
    algo: BaseAlgo = algoConfigClass(
        name=session["short_code"],
        args=(
            session["access_token"],
            session["short_code"],
            user_details.multiple,
        ),
    )
    algo.start()
    while algo.status is not AlgoStatus.INITIATED:
        time.sleep(1)
    return algo


@app.route("/apis/algo/start", methods=["POST"])
def start_algo():
    algo = get_algo(session["short_code"])

    if algo is None or session.get("access_token", None) is None:  # login wasn't done
        return home(session["short_code"])  # login not done
    elif algo is not None:
        if algo.status is not AlgoStatus.STARTED:
            # handler server restart after login
            short_code: str = session["short_code"]
            user_details = get_user_details(short_code)

            load_broker_module(user_details.broker_name)

            broker: Broker = brokers[user_details.broker_name](user_details.__dict__)
            broker.login({})  # fake login
            broker.set_access_token(session["access_token"])
            algo.broker = broker

    algo.start_algo()

    homeUrl = system_config["homeUrl"] + "?algoStarted=true"
    logging.info("Sending redirect url %s in response", homeUrl)
    respData = {"redirect": homeUrl}
    return json.dumps(respData)


# Authentication decorator
def token_required(f: Callable):
    @wraps(f)
    def decorator(*args, **kwargs):
        short_code = kwargs["short_code"]
        algo = get_algo(short_code)
        # ensure the jwt-token is passed with the headers
        if not session.get("short_code", None) == short_code or session.get("access_token", None) is None or algo is None:
            abort(404)
        return f(algo, *args, **kwargs)

    return decorator
