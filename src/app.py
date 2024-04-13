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
flask_app.config.update(
    SESSION_COOKIE_SAMESITE="None",
)

# TODO override with proper config file
server_config: Dict[str, str] = {}
system_config: Dict[str, str] = {"homeUrl": "http://localhost:8080"}


@flask_app.route("/")
def redirect_home():
    return redirect("/me/" + session.get("short_code", "5207"))


def init_logging(filepath: str) -> None:
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
deploy_dir = server_config.get("deploy_dir", "../.deploy/")
if server_config.get("deploy_dir", None) == None:
    server_config["deploy_dir"] = deploy_dir

if os.path.exists(deploy_dir) == False:
    try:
        os.mkdir(deploy_dir)
    except:
        print("Deploy Directory " + deploy_dir + " can't be created. Exiting the app.")
        exit(-1)

logFileDir = server_config.get("logFileDir", deploy_dir + "logs/")
if os.path.exists(logFileDir) == False:
    try:
        os.mkdir(logFileDir)
    except:
        print("LogFile Directory " + logFileDir + " does not exist. Exiting the app.")
        exit(-1)

print("Deploy Directory = " + deploy_dir)
init_logging(logFileDir + "/app.log")

werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.setLevel(logging.ERROR)

port = server_config.get("port", "8080")

flask_app.jinja_env.filters["ctime"] = timectime

flask_app.add_url_rule("/", "default_home", redirect_home)
from views import home
