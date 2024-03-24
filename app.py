import datetime
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, redirect, session

from flask_session import Session

app = Flask(__name__)

app.config["SESSION_TYPE"] = "filesystem"

Session(app)

app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(minutes=180)


@app.route("/")
def redirectHome():
    return redirect("/me/" + session.get("short_code", "5207"))


app.add_url_rule("/", "default_home", redirectHome)


def initLoggingConfg(filepath):
    format = "%(asctime)s: %(message)s"
    handler = TimedRotatingFileHandler(filepath, when="midnight")
    logging.basicConfig(
        handlers=[handler],
        format=format,
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# Execution starts here
serverConfig = {}

deployDir = serverConfig.get("deployDir", "./.deploy/")
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

print("Deploy  Directory = " + deployDir)
print("LogFile Directory = " + logFileDir)
initLoggingConfg(logFileDir + "/app.log")

logging.info("serverConfig => %s", serverConfig)

werkzeugLog = logging.getLogger("werkzeug")
werkzeugLog.setLevel(logging.ERROR)

# brokerAppConfig = getBrokerAppConfig()
# logging.info('brokerAppConfig => %s', brokerAppConfig)

port = serverConfig.get("port", "8080")


def timectime(s):
    if s is None:
        return None
    if isinstance(s, str):
        s = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()
    return datetime.datetime.fromtimestamp(s).strftime("%H:%M:%S")


app.jinja_env.filters["ctime"] = timectime
