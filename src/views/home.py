import importlib
import json
import logging
from functools import wraps
from typing import Callable

from flask import abort, redirect, render_template, request, session

from algos import BaseAlgo, get_algo
from app import flask_app as app
from app import system_config
from broker import BaseLogin, brokers, load_broker_module
from instruments import symbol_to_CMP
from utils import get_user_details


@app.route("/me/<short_code>")
def home(short_code):
    if session.get("short_code", None) is not None and not short_code == session["short_code"]:
        session.clear()
        session["short_code"] = short_code

    if session.get("access_token", None) is None and get_algo(short_code) is None:
        session["short_code"] = short_code
        # special case of server restart and access_token provided via query params
        if request.args.get("access_token", None) is not None:
            session["access_token"] = request.args["access_token"]
            user_details = get_user_details(session["short_code"])
            _initiate_algo(user_details)
            return render_template("main.html")
        return render_template("index.html", broker=get_user_details(short_code).broker)
    else:
        user_details = get_user_details(short_code)
        algo = get_algo(short_code)

        if algo is None:
            algo = _initiate_algo(user_details)

        trademanager = algo.trade_manager
        broker_handler = algo.broker_handler

        return render_template(
            "main.html",
            strategies=trademanager.strategy_to_instance.values() if trademanager is not None else {},
            ltps=symbol_to_CMP[short_code] if trademanager is not None else {},
            algoStarted=True if trademanager is not None else False,
            isReady=True if trademanager is not None and trademanager.is_ready else False,
            # margins=(broker_handler.margins() if broker_handler is not None else {}),
            positions={},  # (broker_handler.positions() if broker_handler is not None else {}),
            orders={},  # (broker_handler.orders() if broker_handler is not None else {}),
            multiple=user_details.multiple,
            short_code=short_code,
        )


@app.route("/apis/broker/login/<broker_name>", methods=["GET", "POST"])
def login(broker_name: str):

    load_broker_module(broker_name)

    short_code: str = session["short_code"]
    user_details = get_user_details(short_code)
    loginHandler: BaseLogin = brokers[broker_name]["LoginHandler"](user_details.__dict__)
    redirectUrl: str = loginHandler.login(request.args)

    if loginHandler.get_access_token() is not None:
        session["access_token"] = loginHandler.access_token
        algo = _initiate_algo(user_details)
        algo.broker_handler = loginHandler.get_broker_handler()

    return redirect(redirectUrl, code=302)


def _initiate_algo(user_details) -> BaseAlgo:
    algoType = user_details.algoType
    algoConfigModule = importlib.import_module("algos")
    algoConfigClass = getattr(algoConfigModule, algoType)
    algo = algoConfigClass(
        name=session["short_code"],
        args=(
            session["access_token"],
            session["short_code"],
            user_details.multiple,
        ),
    )
    algo.start()
    return algo


@app.route("/apis/algo/start", methods=["POST"])
def start_algo():
    algo = get_algo(session["short_code"])
    if algo is None:
        return home(session["short_code"])
    if algo.broker_handler is None:
        user_details = get_user_details(session["short_code"])
        broker_name = user_details.broker
        load_broker_module(broker_name)
        loginHandler: BaseLogin = brokers[broker_name]["LoginHandler"](user_details.__dict__)
        loginHandler.login({})
        loginHandler.set_access_token(session["access_token"])
        algo.broker_handler = loginHandler.broker_handler

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
        trademanager = get_algo(short_code).trade_manager
        # ensure the jwt-token is passed with the headers
        if not session.get("short_code", None) == short_code or session.get("access_token", None) is None or trademanager is None:
            abort(404)
        return f(trademanager, *args, **kwargs)

    return decorator
