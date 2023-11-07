import os
import sys
import json
import shutil
import random
import sqlite3
import asyncio
from typing import *

from time import sleep
from uuid import uuid4, UUID
from flask import Flask, request, jsonify, render_template, abort, redirect, send_from_directory, session, send_file
from flask_compress import Compress
from subprocess import CalledProcessError, Popen, check_output, STDOUT, DEVNULL, PIPE
from datetime import datetime, timedelta, timezone
from threading import Thread
import requests as rq
from dotenv import load_dotenv

from threadSafeBuiltIns import TSSet

try:
    from examinfo import exam_start_time, exam_end_time
except ImportError:
    exam_start_time = datetime.now()
    exam_end_time = datetime.now()


load_dotenv()

app = Flask(__name__)
Compress(app)

if not os.path.isfile("session.key"):
    with open("session.key", "wb") as f:
        f.write(random.randbytes(32))

with open("session.key", "rb") as f:
    app.config["SECRET_KEY"] = f.read()
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SERVER_NAME'] = os.getenv("HOST","127.0.0.1")

class OutputLimitExceedError(Exception):
    cmd = ""


OLE_LEN_MAX = 2**18
OLE_LINE_MAX = 10000


class PopenTimeoutAwait:
    def __init__(self,p:'Popen',timelimit:int|float) -> None:
        self.p = p
        self.t = timedelta(seconds=timelimit)

    def __await__(self):
        deadline = datetime.now() + self.t
        while self.p.poll() is None and datetime.now() < deadline:
            yield

class OutputWriterTokenStorer(TSSet):
    def new_token(self):
        token = str(uuid4())
        self.add(token)
        
        t = Thread(target=lambda x:(sleep(5),self.del_token(x)),args=(token,))
        t.start()
        return token

    def del_token(self,token):
        try:
            self.remove(token)
        except:
            pass

storer = OutputWriterTokenStorer()

def is_during_exam(time:'datetime'|None = None):
    if time is None:
        now = datetime.now(timezone(timedelta(hours=8)))
    else:
        now = time.astimezone()
    return exam_start_time < now < exam_end_time


def need_login(func:Callable) -> Callable:
    def check_login(*awgs, **kwargs):
        if is_guest():
            return abort(401, "沒有登入不能偷看！")
        return func(*awgs, **kwargs)
    check_login.__name__ = func.__name__
    return check_login


def db_login(func:Callable) -> Callable:
    def login(*awgs, **kwargs):
        conn = sqlite3.connect("database/database.db")
        cursor = conn.cursor()
        try:
            res = func(*awgs, cursor=cursor, **kwargs)
        except:
            raise
        else:
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        return res
    login.__name__ = func.__name__
    return login


def get_problem_data() -> dict:
    filename = "data/problems.json"
    if is_during_exam():
        filename = "data/exam.json"
    try:
        with open(filename) as problem_data:
            return json.load(problem_data)
    except:
        return {}

def get_problem_io_file_name(problem_id:str) -> Tuple[str,str]:
    pdata = get_problem_data()
    ifn = pdata.get(problem_id,{}).get("input_fn","input.in")
    ofn = pdata.get(problem_id,{}).get("output_fn","output.out")
    return ifn,ofn

def get_problem_time_limit(problem_id:str) -> int:
    return get_problem_data().get(problem_id,{}).get("timelimit",5)

def get_user_data() -> dict:
    with open("data/users.json", "r") as f:
        return json.load(f)

def get_user_type() -> str:
    stulist = get_user_data()
    query = session.get("id", "guest")
    return stulist.get(query, {}).get("type", "guest")

def is_admin() -> bool:
    return get_user_type() == "admin"

def is_guest() -> bool:
    return get_user_type() == "guest"

flask_render_template = render_template


def my_render_template(template, **kwargs):
    kwargs.update({
        "base_name": "base.html",
        "session":session,
        "problem_data":get_problem_data(),
        "user_data":get_user_data()
    })
    return flask_render_template(
        template,
        **kwargs
    )


render_template = my_render_template


def verify_problem_start_time(problem_id: str):
    problem_data = get_problem_data()
    start_time = problem_data[problem_id].get("start_time")
    return start_time is None\
        or datetime.now(timezone(timedelta(hours=8))) >= datetime.fromisoformat(start_time)\
        or is_admin()


app.add_template_filter(verify_problem_start_time)

@app.add_template_filter
def my_length(s):
    try:
        return len(s)
    except:
        return 0

@app.add_template_filter
def get_problem_desc(problem_id:str):
    if (url:=get_problem_data().get(problem_id,dict()).get("desc_url")) is not None:
        return url
    return f"https://hackmd.io/@{os.getenv('HACKMD_OWNER')}/{get_problem_data().get(problem_id,dict()).get('hackmd',problem_id)}"

@app.add_template_filter
def replace_invicible(s: str):
    return s.replace("\x00", "\u2400").replace(" ", "·")

async def judge(problem_id: str,
                case: int,
                token: 'UUID',
                loop: 'asyncio.AbstractEventLoop'):
    ret_res = {
        "status": "",
        "message": "",
        "score": 0,
        "case": case,
        "log": []
    }

    input_file_name,output_file_name = get_problem_io_file_name(problem_id)

    ans = b""
    try:
        timelimit = get_problem_time_limit(problem_id)
        ans_token = uuid4()
        res_token = uuid4()
        os.makedirs(f"/sandbox/{ans_token}")
        os.chmod(f"/sandbox/{ans_token}",0o777)
        shutil.copy(f"/app/answer/{problem_id}",f"/sandbox/{ans_token}")

        os.link(f"/testcase/{problem_id}/{case}.in",f"/sandbox/{ans_token}/{input_file_name}")

        ansp = Popen(
            [
                "python",
                "-u",
                "jail.py",
                f"/sandbox/{ans_token}",
                "./" + problem_id,
                f"-t_{timelimit}"
            ],
            cwd="/app",
            stderr=PIPE
        )
        await PopenTimeoutAwait(
            ansp,
            timelimit + 1
        )
        
        if ansp.poll() is None or ansp.poll() == 3:
            ansp.kill()
            return ret_res | {
                "status": f"Judge Server Timeout",
                "message": f"Judge server is busy now, try it later and tell admin to restart the server."
            }
        elif ansp.poll() == 2:
            return ret_res | {
                "status": "Judge Runtime Error",
                "message": ansp.stderr.read().decode() if ansp.stderr else ""
            }
        elif ansp.poll() == 1:
            return ret_res | {
                "status": "Unknown Error",
                "message": "Something went wrong. Please content admin to repair it."
            }
        
        try:
            with open(f"/sandbox/{ans_token}/{output_file_name}","rb") as ansf:
                ans = ansf.read()
        except:
            return ret_res | {
                "status": "Judge Runtime Error",
                "message": "Answer output file not found."
            }
        ans = ans.rstrip()
        ans = ans.split(b"\n")
        
        os.makedirs(f"/sandbox/{res_token}")
        os.chmod(f"/sandbox/{res_token}",0o777)

        os.link(f"/sandbox/{token}/main",f"/sandbox/{res_token}/main")

        os.link(f"/testcase/{problem_id}/{case}.in",f"/sandbox/{res_token}/{input_file_name}")

        resp = Popen(
            [
                "python",
                "-u",
                "jail.py",
                f"/sandbox/{res_token}",
                "./main",
                f"-t_{timelimit}"
            ],
            cwd="/app",
            stderr=PIPE
        )
        await PopenTimeoutAwait(
            resp,
            timelimit + 1
        )

        if resp.poll() is None or resp.poll() == 3:
            resp.kill()
            return ret_res | {
                "status": "Time Limit Exceeded"
            }
        elif resp.poll() == 2:
            return ret_res | {
                "status": "Runtime Error",
                "message": resp.stderr.read().decode(errors="replace") if resp.stderr else ""
            }
        elif resp.poll() == 1:
            return ret_res | {
                "status": "Unknown Error",
                "message": "Something went wrong. Please content admin to repair it."
            }
        try:
            with open(f"/sandbox/{res_token}/{output_file_name}","rb") as resf:
                res = resf.read()
        except:
            return ret_res | {
                "status": "Wrong Answer",
                "message": f"Output file \"{output_file_name}\" not found." 
            }
        res = res.rstrip()
        if len(res) > OLE_LEN_MAX:
            return ret_res | {
                "status": "Output Limit Exceeded"
            }
        res = res.split(b"\n")
        if len(res) > OLE_LINE_MAX:
            return ret_res | {
                "status": "Output Limit Exceeded"
            }
        while len(res) < len(ans):
            res.append(None)
        while len(ans) < len(res):
            ans.append(None)
        for r, a, c in zip(res, ans, range(1, len(ans)+1)):
            if a is None or r is None or r.rstrip() != a.rstrip():
                def decode_rstrip(x): return None if x is None else x.decode(errors='replace') #.rstrip()

                return ret_res | {
                    "status": "Wrong Answer",
                    "log": list(zip(
                        map(decode_rstrip, res),
                        map(decode_rstrip, ans)
                    ))
                }
        else:
            return ret_res | {
                "status": "Accepted",
                "score": 100
            }
    
    except Exception as e:
        return ret_res | {
            "status": f"Unknown error",
            "message": f"{type(e).__name__},{str(e)}"
        }
    
    finally:
        clear_sandbox(res_token)
        clear_sandbox(ans_token)


@app.route("/results/<int:date>/<string:res_id>", strict_slashes=False)
@need_login
def get_res(date: int = 0, res_id: str = ""):
    if os.path.isfile(f"results/{date:08d}/{res_id}.json"):
        with open(f"results/{date:08d}/{res_id}.json", "r") as f:
            resp = json.load(f)
            if is_during_exam() and\
                    not is_during_exam(datetime.strptime(resp["time"], "%Y/%m/%d %H:%M:%S")) and\
                    not is_admin():
                return abort(403, "考試中不能查看這個結果。")
            if resp["author"] != session.get("id") and not is_admin():
                return abort(403, "還想偷看別人的結果ㄚ。")
            return render_template("result.html", **resp)
    return abort(404)


@app.route("/api/judge", methods=["POST"], strict_slashes=False)
@need_login
def post_judge():
    while True:
        filebytes = b""
        today = datetime.now(timezone(timedelta(hours=8)))
        token = uuid4()
        os.makedirs(f"/sandbox/{token}")
        problem_id = request.form.get("problem_id", "")
        language = request.form.get("language","C")
        language = "C++" if language == "C++" else "C"
        author = session.get("id", "guest")
        resp = {
            "token": str(token),
            "author": author,
            "problem_id": problem_id,
            "client_ip": request.headers.get("Cf-Connecting-Ip", request.headers.get("X-Forwarded-For", "Unknown")),
            "message": "Judging",
            "score": 0,
            "code": "",
            "time": today.strftime("%Y/%m/%d %H:%M:%S"),
            "logs": [],
            "auto": session.get("auto",0),
            "language": language
        }

        resp.update(session)

        p = today.strftime("%Y%m%d")

        # begin submit file part

        submit_type = request.form.get("submit_type", "file")
        if submit_type == "file":
            file = request.files.get("file", None)
            if file is None or file.filename == "":
                return abort(400, "No file submit.")
            filebytes = file.read()
        elif submit_type == "text":
            text = request.form.get("text", "")
            filebytes = text.encode()
        else:
            return abort(400, "Unknown submit type.")
        resp["code"] = filebytes.decode(errors="replace")

        if problem_id == "" or not os.path.isdir(f"testcase/{problem_id}"):
            return abort(404, "題目不存在。")

        with open(f"/sandbox/{token}/main.c", "wb") as f:
            if os.path.isfile(f"code_template/{problem_id}/prepend.c"):
                with open(f"code_template/{problem_id}/prepend.c", "rb") as fp:
                    f.write(fp.read())
            f.write(filebytes)
            if os.path.isfile(f"code_template/{problem_id}/append.c"):
                with open(f"code_template/{problem_id}/append.c", "rb") as fp:
                    f.write(fp.read())
        
        r = rq.post(
            f"http://{os.getenv('OW_HOST')}:{os.getenv('OW_PORT')}/add_result/{p}/{token}",
            json={
                "data": json.dumps(resp, indent=4, ensure_ascii=False),
                "token":storer.new_token()
            }
        )
        if r.status_code != 200:
            raise

        try:
            for _ in range(50):
                if os.path.isfile(f"/sandbox/{token}/main.c"):
                    break
                sleep(0.1)
            check_output(
                [
                    "g++" if language == "C++" else "gcc",
                    "main.c",
                    "-std=c++20" if language == "C++" else "-std=c17",
                    "-static", "-lm",
                    "-fmax-errors=5",
                    "-Werror",
                    "-o", f"/sandbox/{token}/main"
                ],
                stderr=STDOUT,
                cwd=f"/sandbox/{token}"
            )
        except CalledProcessError as e:
            resp["message"] = f"Compile Error\n{e.output.decode(errors='replace')}"
            break

        score = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks = []
        if request.form.get("custom_testcase", "False") == "True":
            return abort(410,"custom testcase was deprecation.")
        else:
            for i in range(1,101):
                inputfile = f"testcase/{problem_id}/{i}.in"
                if os.path.isfile(inputfile):
                    os.system("rsync -a /app/testcase/")

                    tasks.append(
                        loop.create_task(
                            judge(
                                problem_id=problem_id,
                                case=i,
                                token=token,
                                loop=loop
                            )
                        )
                    )
                else:
                    break
        all_res = loop.run_until_complete(asyncio.gather(*tasks))
        all_res.sort(key=lambda x: x["case"])
        score = sum(map(lambda x: x["score"], all_res)) // len(all_res)
        resp.update({"logs": all_res})
        if score == 100:
            resp.update({"score": score, "message": "Accepted"})
        elif score != 0:
            resp.update({"score": score, "message": "Partial Accepted"})
        else:
            status_priority = {
                "Wrong Answer": 1,
                "Runtime Error": 2,
                "Time Limit Exceeded": 3,
                "Output Limit Exceeded": 4
            }
            status_list = sorted(
                map(lambda x: x["status"], all_res),
                key=lambda x: status_priority.get(x, 0)
            )

            resp.update({"score": score, "message": status_list[0]})

        break
    clear_sandbox(token)
    r = rq.post(f"http://{os.getenv('OW_HOST')}:{os.getenv('OW_PORT')}/exec_sql", json={
        "command": "INSERT INTO `results` VALUES(?,?,?,?,?,?,?)",
        "params": [
            resp["author"],
            resp["problem_id"],
            str(token),
            today.strftime("%Y-%m-%d %H:%M:%S"),
            resp["message"].split("\n")[0],
            int(resp["auto"]),
            language
        ],
        "token":storer.new_token()
    })
    if r.status_code != 200:
        raise

    r = rq.post(f"http://{os.getenv('OW_HOST')}:{os.getenv('OW_PORT')}/add_result/{p}/{token}", json={
        "data": json.dumps(resp, ensure_ascii=False),
        "token":storer.new_token()
    })
    if r.status_code != 200:
        raise

    if request.form.get("browser") == "True":
        return redirect(f"/results/{p}/{token}"), 302

    return jsonify(resp)


@app.route("/testcases", strict_slashes=False)
@app.route("/testcases/<string:problem_id>", strict_slashes=False)
@app.route("/testcases/<string:problem_id>/<int:case_no>", strict_slashes=False)
@need_login
def all_testcase(problem_id=None, case_no=None):

    if problem_id is None:
        return render_template(
            "testcase_all.html",
        )
    elif problem_id not in get_problem_data():
        return abort(404)
    elif not verify_problem_start_time(problem_id):
        return abort(403, "Exam is not start yet.")
    elif case_no is None:
        if os.path.isdir(f"testcase/{problem_id}"):
            cases=[i[:-3] for i in os.listdir(f"testcase/{problem_id}") if (
                    os.path.isfile(f"testcase/{problem_id}/{i}") and i[-3:] == ".in" and i[:-3].isdigit())]
            cases.sort(key=int)
            contents = {}
            for case in cases:
                if os.path.isfile(f"testcase/{problem_id}/{case}.in"):
                    with open(f"testcase/{problem_id}/{case}.in", "r") as f:
                        contents[case] = f.read()
            return render_template(
                "testcase_list.html",
                problem_id=problem_id,
                cases=cases,
                contents = contents
            )
        else:
            return abort(404)
    elif os.path.isfile(f"testcase/{problem_id}/{case_no}.in"):
        if request.args.get("download") is not None:
            return send_file(f"testcase/{problem_id}/{case_no}.in",as_attachment=True,download_name=f"{problem_id}_case{case_no}.in.txt")
        with open(f"testcase/{problem_id}/{case_no}.in", "r") as f:
            return render_template(
                "testcase.html",
                problem_id=problem_id,
                case_no=case_no,
                content=f.read()
            )
    else:
        return abort(404, "測資或題目不存在。")


@app.route("/results", strict_slashes=False)
@db_login
@need_login
def results(cursor: 'sqlite3.Cursor'):
    url_params = dict(request.args)

    page = url_params.get("page", "")
    page = max(int(page), 1) if page.isdigit() else 1
    line = url_params.get("line", "")
    line = max(int(line), 0) if line.isdigit() else 20


    conditions = []
    cond_params = []

    if url_params.get("self_only") == "1" or (url_params.get("self_only", "") == "" and not is_admin()):
        stu_id = session.get("id")
        conditions.append("user_id = ?")
        cond_params.append(stu_id)

    if url_params.get("auto") == "1":
        conditions.append("auto = 1")

    if url_params.get("noauto") == "1":
        conditions.append("auto = 0")

    stu_id = url_params.get("user_id")
    if stu_id:
        conditions.append("user_id = ?")
        cond_params.append(stu_id)

    problem_id = url_params.get("problem_id")
    if problem_id:
        conditions.append("problem_id = ?")
        cond_params.append(problem_id)

    start_time = url_params.get("start_time")
    if start_time:
        try:
            start_time = datetime.fromisoformat(start_time).astimezone()
        except:
            start_time = None

    end_time = url_params.get("end_time")
    if end_time:
        try:
            end_time = datetime.fromisoformat(end_time).astimezone()
        except:
            end_time = None

    if is_during_exam() and not is_admin():
        if not (start_time and start_time > exam_start_time):
            start_time = exam_start_time
        if not (end_time and end_time < exam_end_time):
            end_time = exam_end_time

    if start_time:
        conditions.append("time >= ?")
        cond_params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

    if end_time:
        conditions.append("time <= ?")
        cond_params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

    status = url_params.get("status")
    if status:
        conditions.append("status = ?")
        cond_params.append(status)

    query = ""

    if len(conditions) > 0:
        query += " WHERE "
    query += " AND ".join(conditions)
    total_query = "SELECT count(*) FROM `results` " + query
    total = cursor.execute(total_query, tuple(cond_params)).fetchall()[0][0]
    query += " ORDER BY `time` DESC LIMIT ? OFFSET ?"
    cond_params.append(line if page > 0 else 0)
    cond_params.append((page-1)*line)

    query = "SELECT * FROM `results` " + query

    res = cursor.execute(
        query,
        tuple(cond_params)
    )

    data = res.fetchall()

    return render_template(
        "result_list.html",
        is_admin=is_admin(),
        url_params=url_params,
        results=data,
        total=total,
        page=page,
        line=line,
        all_status=["Accepted", "Partial Accepted", "Wrong Answer", "Compile Error", "Runtime Error",
                    "Time Limit Exceeded", "Output Limit Exceeded"]
    )


@app.route("/problems/<string:problem_id>", methods=["GET"], strict_slashes=False)
def problem(problem_id: str = ""):
    problem_data = get_problem_data()
    if problem_id not in problem_data:
        return abort(404, "找不到題目.")
    if not verify_problem_start_time(problem_id):
        return abort(403, "本題尚未開放.")

    return render_template(
        "problem.html",
        problem_id=problem_id
    )


@app.route("/", strict_slashes=False)
def index():
    if len(request.args) != 0:
        return redirect("/",302)
    return render_template("index.html")


@app.route("/problems", strict_slashes=False)
@need_login
def problem_list():
    return render_template("problem_list.html")


@app.route("/assets/<path:fn>", strict_slashes=False)
def assets(fn):
    return send_from_directory("assets", fn)


@app.route("/demo_login", methods=["GET"], strict_slashes=False)
def demo_login():
    return render_template("demo_login.html")

@app.route("/demo_login/<string:username>", methods=["GET"], strict_slashes=False)
def demo_user_login(username):
    if username in get_user_data():
        session["id"] = "username"
        session["name"] = get_user_data().get(username,{}).get("name","")


@app.route("/logout", strict_slashes=False)
def logout():
    session.clear()
    return "<script>alert('登出成功');window.history.back();</script>"


@app.route("/check", strict_slashes=False)
def chk_session():
    return session.get("id", "none")

@app.route("/test")
def test():
    return render_template("test.html")


@app.route("/verify_token",methods=["GET"])
def verify_token_get():
    return abort(404)


@app.route("/verify_token",methods=["POST"])
def verify_token():
    if request.headers.get("user-agent") != os.getenv('OW_USER_AGENT'):
        return abort(404)
    token = request.json.get("token")
    if token in storer:
        storer.del_token(token)
        return ""
    return "",404

@app.route("/base")
def base():
    return render_template("base.html")

@app.before_first_request
def clear_sandbox(token="*"):
    Popen(f"rm -r /sandbox/{token}", shell=True, stdout=DEVNULL, stderr=DEVNULL)


@app.before_request
def before_req():
    request.time = datetime.now()
    request.print_info = True
    
    if request.headers.get("user-agent") == os.getenv("AUTO_USER_AGENT"):
        session["auto"] = 1
        session["author"] = request.form.get("author")
        session["id"] = request.form.get("author")


@app.errorhandler(Exception)
def errorhandler(error):
    try:
        return render_template("error.html", err=error), error.code
    except:
        if request.headers.get("user-agent") == os.getenv("AUTO_USER_AGENT")\
        or is_admin():
            raise
        class tmp:
            name = "Internal Server Error"
            description = "伺服器某個地方炸了，請通知管理員處理。"
        return render_template("error.html", err=tmp()), 500


if __name__ == "__main__":
    app.run(threaded=True, host="0.0.0.0", port=443, ssl_context=("server.crt","server.key"))
