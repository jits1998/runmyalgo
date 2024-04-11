import asyncio

from flask import redirect, request, url_for

from app import flask_app as app
from core.strategy import ManualStrategy
from instruments import get_instrument_data_by_symbol
from models import TradeExitReason
from utils import prepare_weekly_options_symbol
from views.home import get_algo, token_required


@token_required
@app.route("/me/<short_code>/strategy/exit/<name>")
def exit_strategy(trademanager, short_code, name):

    trademanager.squareOffStrategy(trademanager.strategyToInstanceMap[name], TradeExitReason.MANUAL_EXIT)

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/trade/exit/<id>")
def exit_trade(trademanager, short_code, id):
    name = id.split(":")[0]

    trades = trademanager.getAllTradesByStrategy(name)

    for trade in trades:
        if trade.tradeID == id:
            trademanager.squareOffTrade(trade, TradeExitReason.MANUAL_EXIT)

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/trade/enter", methods=["POST"])
def enter_trade(trademanager, short_code):
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

    trading_symbol = prepare_weekly_options_symbol(ul, strike, iType, expiryDay=int(expiryDay))
    isd = get_instrument_data_by_symbol(short_code, trading_symbol)  # Get instrument data to know qty per lot
    numLots = int(quantity) // isd["lot_size"]

    asyncio.run_coroutine_threadsafe(
        ms.generateTrade(
            trading_symbol,
            direction,
            numLots,
            (trigger if trigger > 0 else price),
            slPrice=sl,
            targetPrice=target,
            placeMarketOrder=(False if trigger > 0 else True),
        ),
        get_algo(short_code).loop,
    )

    return redirect(url_for("home", short_code=short_code))


@token_required
@app.route("/me/<short_code>/get_quote")
def get_quote(trademanager, short_code):
    ms = ManualStrategy.getInstance(short_code=short_code)
    ul = request.args["index"]
    strike = request.args["strike"]
    iType = request.args["type"]
    expiryDay = request.args["expiryDay"]
    trading_symbol = prepare_weekly_options_symbol(ul, strike, iType, expiryDay=int(expiryDay))
    quote = ms.get_quote(trading_symbol)

    return str(quote.lastTradedPrice)
