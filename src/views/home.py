import importlib
from functools import wraps
from typing import Callable

from flask import abort, redirect, render_template, request, session

from app import flask_app as app
from broker import BaseLogin, brokers, load_broker_module
from models import UserDetails
from utils import getBrokerLogin, getTradeManager, getUserDetails


@app.route("/me/<short_code>")
def home(short_code):
    if session.get("short_code", None) is not None and not short_code == session["short_code"]:
        session.clear()
        session["short_code"] = short_code

    if session.get("access_token", None) is None and getTradeManager(short_code) is None:
        session["short_code"] = short_code
        if request.args.get("accessToken", None) is not None:
            session["access_token"] = request.args["accessToken"]
            return render_template("index_algostarted_new.html")
        return render_template("index.html", broker=getUserDetails(short_code).broker)
    else:
        trademanager = getTradeManager(short_code)
        brokerLogin = getBrokerLogin(short_code)
        userDetails = getUserDetails(short_code)
        return render_template(
            "main.html",
            strategies=trademanager.strategyToInstanceMap.values() if trademanager is not None else {},
            ltps=trademanager.symbolToCMPMap if trademanager is not None else {},
            algoStarted=True if trademanager is not None else False,
            isReady=True if trademanager is not None and trademanager.isReady else False,
            margins=(brokerLogin.getBrokerHandle().margins() if brokerLogin is not None else {}),
            positions=(brokerLogin.getBrokerHandle().positions() if brokerLogin is not None else {}),
            orders=(brokerLogin.getBrokerHandle().orders() if brokerLogin is not None else {}),
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
        userDetails.start()
        userDetails.loginHandler = loginHandler

    return redirect(redirectUrl, code=302)


@app.route("/apis/algo/start", methods=["POST"])
def startAlgo():
    if not getTradeManager(short_code=session["short_code"]):
        # get User's Algo type
        userDetails = getUserDetails(session["short_code"])
        algoType = userDetails.algoType
        algoConfigModule = importlib.import_module("algos")
        algoConfigClass = getattr(algoConfigModule, algoType)

        algoConfigClass().startAlgo(session["access_token"], session["short_code"], userDetails.multiple)

        # start algo in a separate thread
        x = threading.Thread(
            target=algoConfigClass().startAlgo,
            name="Algo",
            args=(
                session["access_token"],
                session["short_code"],
                getBrokerAppConfig(session["short_code"]).get("multiple", 1),
            ),
        )

        x.start()
        while x.is_alive():
            time.sleep(1)
    systemConfig = getSystemConfig()
    homeUrl = systemConfig["homeUrl"] + "?algoStarted=true"
    logging.info("Sending redirect url %s in response", homeUrl)
    respData = {"redirect": homeUrl}
    return json.dumps(respData)


# Authentication decorator
def token_required(f: Callable):
    @wraps(f)
    def decorator(*args, **kwargs):
        short_code = kwargs["short_code"]
        trademanager = getTradeManager(short_code)
        # ensure the jwt-token is passed with the headers
        if not session.get("short_code", None) == short_code or session.get("access_token", None) is None or trademanager is None:
            abort(404)
        return f(trademanager, *args, **kwargs)

    return decorator
