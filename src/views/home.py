import importlib
import json
import logging
import threading
from functools import wraps
from typing import Callable, Union

from flask import abort, redirect, render_template, request, session

from algos import BaseAlgo, getAlgo
from app import flask_app as app
from broker import BaseLogin, brokers, load_broker_module
from config import getUserConfig
from models.user import UserDetails
from utils import getUserDetails


@app.route("/me/<short_code>")
def home(short_code):
    if session.get("short_code", None) is not None and not short_code == session["short_code"]:
        session.clear()
        session["short_code"] = short_code

    if session.get("access_token", None) is None and getAlgo(short_code) is None:
        session["short_code"] = short_code
        # special case of server restart and accessToken provided via query params
        if request.args.get("accessToken", None) is not None:
            session["access_token"] = request.args["accessToken"]
            userDetails = getUserDetails(session["short_code"])
            _initiateAlgo(userDetails)
            return render_template("main.html")
        return render_template("index.html", broker=getUserDetails(short_code).broker)
    else:
        userDetails = getUserDetails(short_code)
        algo = getAlgo(short_code)

        if algo is None:
            algo = _initiateAlgo(userDetails)

        trademanager = algo.tradeManager
        brokerHandler = algo.brokerHandler

        return render_template(
            "main.html",
            strategies=trademanager.strategyToInstanceMap.values() if trademanager is not None else {},
            ltps=trademanager.symbolToCMPMap if trademanager is not None else {},
            algoStarted=True if trademanager is not None else False,
            isReady=True if trademanager is not None and trademanager.isReady else False,
            # margins=(brokerHandler.margins() if brokerHandler is not None else {}),
            # positions=(brokerHandler.positions() if brokerHandler is not None else {}),
            # orders=(brokerHandler.orders() if brokerHandler is not None else {}),
            multiple=userDetails.multiple,
            short_code=short_code,
        )


@app.route("/apis/broker/login/<broker_name>", methods=["GET", "POST"])
def login(broker_name: str):

    load_broker_module(broker_name)

    short_code: str = session["short_code"]
    userDetails = getUserDetails(short_code)
    loginHandler: BaseLogin = brokers[broker_name]["LoginHandler"](userDetails.__dict__)
    redirectUrl: str = loginHandler.login(request.args)

    if loginHandler.getAccessToken() is not None:
        session["access_token"] = loginHandler.accessToken
        x = _initiateAlgo(userDetails)
        x.brokerHandler = loginHandler.getBrokerHandler()

    return redirect(redirectUrl, code=302)


def _initiateAlgo(userDetails) -> BaseAlgo:
    algoType = userDetails.algoType
    algoConfigModule = importlib.import_module("algos")
    algoConfigClass = getattr(algoConfigModule, algoType)
    x = algoConfigClass(
        name=session["short_code"],
        args=(
            session["access_token"],
            session["short_code"],
            userDetails.multiple,
        ),
    )
    x.start()
    return x


@app.route("/apis/algo/start", methods=["POST"])
def startAlgo():
    algo = getAlgo(session["short_code"])
    if algo.brokerHandler is None:
        userDetails = getUserDetails(session["short_code"])
        broker_name = userDetails.broker
        load_broker_module(broker_name)
        loginHandler: BaseLogin = brokers[broker_name]["LoginHandler"](userDetails.__dict__)
        loginHandler.login({})
        loginHandler.setAccessToken(session["access_token"])
        algo.brokerHandler = loginHandler.brokerHandler

    algo.startAlgo()
    systemConfig = app.getSystemConfig()
    homeUrl = systemConfig["homeUrl"] + "?algoStarted=true"
    logging.info("Sending redirect url %s in response", homeUrl)
    respData = {"redirect": homeUrl}
    return json.dumps(respData)


# Authentication decorator
def token_required(f: Callable):
    @wraps(f)
    def decorator(*args, **kwargs):
        short_code = kwargs["short_code"]
        trademanager = getAlgo(short_code).tradeManager
        # ensure the jwt-token is passed with the headers
        if not session.get("short_code", None) == short_code or session.get("access_token", None) is None or trademanager is None:
            abort(404)
        return f(trademanager, *args, **kwargs)

    return decorator


def getBrokerLogin(short_code: str) -> Union[BaseLogin, None]:
    for t in threading.enumerate():
        if t.getName() == short_code:
            algo: BaseAlgo = t  # type: ignore
            return algo.loginHandler
    return None
