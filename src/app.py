import datetime
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, Union

from flask import Flask, redirect, session

from flask_session import Session  # type: ignore

flask_app = Flask(__name__)
flask_app.config["SESSION_TYPE"] = "filesystem"
Session(flask_app)
flask_app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(minutes=180)

# TODO override with proper config file
serverConfig: Dict[str, str] = {}
systemConfig: Dict[str, str] = {"homeUrl": "http://localhost:8080"}


@flask_app.route("/")
def redirectHome():
    return redirect("/me/" + session.get("short_code", "5207"))


def initLoggingConfg(filepath: str) -> None:
    format = "%(asctime)s: %(message)s"
    handler = TimedRotatingFileHandler(filepath, when="midnight")
    logging.basicConfig(
        handlers=[handler],
        format=format,
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def timectime(s: Union[str, float]) -> str:
    if s is None:
        return None
    if isinstance(s, str):
        s = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()
    return datetime.datetime.fromtimestamp(s).strftime("%H:%M:%S")


# Execution starts here
deployDir = serverConfig.get("deployDir", "../.deploy/")
if serverConfig.get("deployDir", None) == None:
    serverConfig["deployDir"] = deployDir

if os.path.exists(deployDir) == False:
    try:
        os.mkdir(deployDir)
    except:
        print("Deploy Directory " + deployDir + " can't be created. Exiting the app.")
        exit(-1)

logFileDir = serverConfig.get("logFileDir", deployDir + "logs/")
if os.path.exists(logFileDir) == False:
    try:
        os.mkdir(logFileDir)
    except:
        print("LogFile Directory " + logFileDir + " does not exist. Exiting the app.")
        exit(-1)

print("Deploy Directory = " + deployDir)
initLoggingConfg(logFileDir + "/app.log")

werkzeugLog = logging.getLogger("werkzeug")
werkzeugLog.setLevel(logging.ERROR)

# brokerAppConfig = getBrokerAppConfig()
# logging.info('brokerAppConfig => %s', brokerAppConfig)

port = serverConfig.get("port", "8080")

flask_app.jinja_env.filters["ctime"] = timectime

flask_app.add_url_rule("/", "default_home", redirectHome)
from views import home
