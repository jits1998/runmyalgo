from functools import wraps

from flask import abort, render_template, request, session

from app import flask_app as app
from config import getUserConfig
from utils import getTradeManager


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
        return render_template("index.html", broker=getUserConfig(short_code).get("broker", "zerodha"))


# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        short_code = kwargs["short_code"]
        trademanager = getTradeManager(short_code)
        # ensure the jwt-token is passed with the headers
        if (
            not session.get("short_code", None) == short_code
            or session.get("access_token", None) is None
            or trademanager is None
        ):
            abort(404)
        return f(trademanager, *args, **kwargs)

    return decorator
