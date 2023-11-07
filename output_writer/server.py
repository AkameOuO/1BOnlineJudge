from flask import Flask, request
from os import makedirs, getenv
from dotenv import load_dotenv
import requests as rq
import sqlite3
import sys

load_dotenv()
app = Flask(__name__)

def db_login(func):
    def login(*awgs,**kwargs):
        conn = sqlite3.connect(f"/output/database/database.db")
        cursor = conn.cursor()
        try:
            res = func(*awgs,cursor=cursor,**kwargs)
        finally:
            conn.commit()
            cursor.close()
            conn.close()
        return res
    login.__name__ = func.__name__
    return login


@app.route("/add_result/<string:date>/<string:token>",methods=["POST"])
def add_result(date,token):
    try:
        makedirs(f"/output/results/{date}")
    except:
        pass
    with open(f"/output/results/{date}/{token}.json","w") as f:
        f.write(request.json.get("data"))
    return ""

@app.route("/exec_sql",methods=["POST"])
@db_login
def exec_sql(cursor):
    cursor.execute(request.json.get("command"),tuple(request.json.get("params")))
    return ""

@app.before_request
def before_req():
    token = request.json.get("token")
    print(token,file=sys.stderr)
    if not token:
        return "" ,403
    r = rq.post(f"https://{getenv('MAIN_HOST')}/verify_token",json={"token":token},headers={"user-agent":getenv("OW_USER_AGENT")},verify="server.pem")
    if r.status_code != 200:
        return "" ,403

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=getenv("OW_PORT"),debug=True)