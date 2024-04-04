import asyncio

from flask import redirect, request, url_for

from app import flask_app as app
from core.strategy import ManualStrategy
from instruments import getInstrumentDataBySymbol
from models import TradeExitReason
from utils import prepareWeeklyOptionsSymbol
from views.home import getAlgo, token_required


@token_required
@app.route("/me/<short_code>/strategy/exit/<name>")
def exitStrategy(trademanager, short_code, name):

    trademanager.squareOffStrategy(trademanager.strategyToInstanceMap[name], TradeExitReason.MANUAL_EXIT)

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/trade/exit/<id>")
def exitTrade(trademanager, short_code, id):
    name = id.split(":")[0]

    trades = trademanager.getAllTradesByStrategy(name)

    for trade in trades:
        if trade.tradeID == id:
            trademanager.squareOffTrade(trade, TradeExitReason.MANUAL_EXIT)

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/trade/enter", methods=["POST"])
def enterTrade(trademanager, short_code):
    ms = ManualStrategy.getInstance(short_code=short_code)
    ul = request.form["index"]
    strike = request.form["strike"]
    iType = request.form["type"]
    expiryDay = request.form["expiryDay"]
    trigger = float(request.form["trigger"])
    sl = float(request.form["sl"])
    price = float(request.form["price"])
    target = float(request.form["target"])
    direction = request.form["direction"]
    quantity = request.form["qty"]

    tradingSymbol = prepareWeeklyOptionsSymbol(ul, strike, iType, expiryDay=int(expiryDay))
    isd = getInstrumentDataBySymbol(short_code, tradingSymbol)  # Get instrument data to know qty per lot
    numLots = int(quantity) // isd["lot_size"]

    asyncio.run_coroutine_threadsafe(
        ms.generateTrade(
            tradingSymbol,
            direction,
            numLots,
            (trigger if trigger > 0 else price),
            slPrice=sl,
            targetPrice=target,
            placeMarketOrder=(False if trigger > 0 else True),
        ),
        getAlgo(short_code).loop,
    )

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/getQuote")
def getQuote(trademanager, short_code):
    ms = ManualStrategy.getInstance(short_code=short_code)
    ul = request.args["index"]
    strike = request.args["strike"]
    iType = request.args["type"]
    expiryDay = request.args["expiryDay"]
    tradingSymbol = prepareWeeklyOptionsSymbol(ul, strike, iType, expiryDay=int(expiryDay))
    quote = ms.getQuote(tradingSymbol)

    return str(quote.lastTradedPrice)
