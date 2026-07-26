# -*- coding: utf-8 -*-
"""
YNU 抢课助手 · Linux 无界面版（服务器挂机用）
=============================================
和图形版共用同一套抢课引擎（登录 / 验证码OCR / 齐射并发 / 高峰增强 / 定时 / 自动重登），
只是把界面换成「配置文件 + 命令行」，适合上传到 Linux 服务器长期挂机。

用法（先激活虚拟环境）：
  python qiangke_cli.py batches                # 列出选课批次，拿到 batch 码
  python qiangke_cli.py query 0 数据结构       # 按分类(0~4)+关键词查课，拿到 教学班ID / type
  python qiangke_cli.py selected               # 看已选课程
  python qiangke_cli.py withdraw <教学班ID>    # 退选
  python qiangke_cli.py run                    # 按 config.json 开始抢课（长期挂机）

配置文件默认同目录 config.json，可用 -c/--config 指定；日志默认同时打到屏幕与 qiangke.log。
依赖： pip install requests ddddocr yagmail   （服务器请装 opencv-python-headless，见 setup.sh）
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except Exception:
    requests = None
try:
    import ddddocr
except Exception:
    ddddocr = None
try:
    import yagmail
except Exception:
    yagmail = None
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:
    HTTPAdapter = None
    Retry = None

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
TIMEOUT = 10                  # 抢课/登录：短超时，快速失败重发
QTIMEOUT = (10, 40)           # 查询/批次：连接10s、读取40s（学校服务器查询较慢）

MODES = {
    "turbo":  {"salvo": 6, "interval": 0.0},
    "fast":   {"salvo": 1, "interval": 0.3},
    "steady": {"salvo": 1, "interval": 2.0},
}

# (显示名, 接口文件, teachingClassType)
QUERY_CATS = [
    ("通识选修课 (XGXK)", "publicCourse.do",      "XGXK"),
    ("推荐课程 (TJKC)",   "recommendedCourse.do", "TJKC"),
    ("主修课程 (FANKC)",  "programCourse.do",     "FANKC"),
    ("体育课程 (TYKC)",   "programCourse.do",     "TYKC"),
    ("创新创业 (CXKC)",   "programCourse.do",     "CXKC"),
]

DEFAULT_BATCH = "77c2465143574415b3c76a820384eab1"

log = logging.getLogger("qiangke")


# ============================ 抢课引擎（与图形版完全一致） ============================
class GrabEngine:
    def __init__(self, log_fn, event_fn):
        self.log = log_fn
        self.event = event_fn
        self.session = None
        self.token = None
        self.weu = None
        self.jsession = None
        self.auth_lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.total_count = 0
        self.count_lock = threading.Lock()
        self.ocr = None

    def build_session(self):
        s = requests.Session()
        if HTTPAdapter is not None:
            retry = None
            if Retry is not None:
                retry = Retry(total=2, connect=2, read=0, backoff_factor=0.1,
                              status_forcelist=[], raise_on_status=False)
            adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=retry)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
        s.headers.update({"User-Agent": UA})
        return s

    def ensure_session(self):
        if self.session is None:
            self.session = self.build_session()
        return self.session

    def get_ocr(self):
        if self.ocr is None:
            with open(os.devnull, "w") as fnull:
                with redirect_stdout(fnull):
                    self.ocr = ddddocr.DdddOcr()
        return self.ocr

    def login(self, username, password):
        try:
            ts = int(time.time() * 1000)
            url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/4/vcode.do?timestamp={ts}"
            r = self.session.get(url, headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "http://xk.ynu.edu.cn/", "X-Requested-With": "XMLHttpRequest"}, timeout=TIMEOUT)
            vtoken = r.json()["data"]["token"]
            url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/vcode/image.do?vtoken={vtoken}"
            r = self.session.get(url, headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://xk.ynu.edu.cn/", "X-Requested-With": "XMLHttpRequest"}, timeout=TIMEOUT)
            code = self.get_ocr().classification(r.content)
            ts = int(time.time() * 1000)
            url = (f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/check/login.do?"
                   f"timestrap={ts}&loginName={username}&loginPwd={password}&verifyCode={code}&vtoken={vtoken}")
            r = self.session.get(url, headers={
                "Accept": "*/*", "Referer": "https://xk.ynu.edu.cn/", "X-Requested-With": "XMLHttpRequest"}, timeout=TIMEOUT)
            if r.status_code == 200 and str(r.json().get("code")) == "1":
                self.log("登录成功")
                return (r.json()["data"]["token"], r.cookies.get("_WEU"), r.cookies.get("JSESSIONID"))
            self.log(f"登录失败（验证码={code}）：{r.text[:120]}")
            return None, None, None
        except Exception as e:
            self.log(f"登录异常：{e}")
            return None, None, None

    def ensure_login(self, username, password, tries=3):
        self.ensure_session()
        with self.auth_lock:
            if self.token is not None:
                return True
            for _ in range(tries):
                t, w, j = self.login(username, password)
                if t is not None:
                    self.token, self.weu, self.jsession = t, w, j
                    return True
                time.sleep(1)
        return self.token is not None

    def invalidate_auth(self):
        with self.auth_lock:
            self.token = None

    def _std_headers(self):
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "token": self.token, "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://xk.ynu.edu.cn", "Referer": "https://xk.ynu.edu.cn/",
        }

    def _cookies(self):
        return {"_WEU": self.weu, "JSESSIONID": self.jsession}

    @staticmethod
    def _parse_item(item, teaching_type, default_batch):
        out = []
        tclist = item.get("tcList")
        subs = tclist if tclist else [item]
        for tc in subs:
            cap = tc.get("classCapacity") or item.get("classCapacity")
            sel = tc.get("numberOfSelected") or item.get("numberOfSelected")
            try:
                remain = int(cap) - int(sel)
            except (TypeError, ValueError):
                remain = None
            out.append({
                "courseName": item.get("courseName") or tc.get("courseName") or "",
                "teacherName": tc.get("teacherName") or item.get("teacherName") or "",
                "teachingClassID": tc.get("teachingClassID"),
                "teachingClassType": teaching_type,
                "remain": remain,
                "isFull": str(tc.get("isFull")),
                "isConflict": str(tc.get("isConflict")),
                "conflictDesc": tc.get("conflictDesc") or item.get("conflictDesc") or "",
                "place": tc.get("teachingPlace") or item.get("teachingPlace") or "",
                "cat": (item.get("publicCourseTypeName") or item.get("typeName")
                        or item.get("courseTypeName") or ""),
                "batch": tc.get("electiveBatchCode") or item.get("electiveBatchCode") or default_batch,
            })
        return out

    def query_courses(self, cfg, endpoint, teaching_type, keyword, page_size=200, max_pages=50):
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return [], "登录失败，无法查询"
        url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/{endpoint}"
        results, got, page = [], 0, 0
        while page < max_pages:
            setting = {
                "data": {"studentCode": cfg["username"], "campus": cfg.get("campus", "02"),
                         "electiveBatchCode": cfg["batch"], "isMajor": "1",
                         "teachingClassType": teaching_type, "checkConflict": "2",
                         "checkCapacity": "2", "queryContent": keyword or ""},
                "pageSize": str(page_size), "pageNumber": str(page), "order": "",
            }
            body = "querySetting=" + requests.utils.quote(json.dumps(setting, ensure_ascii=False))
            try:
                r = self.session.post(url, headers=self._std_headers(), data=body,
                                      cookies=self._cookies(), timeout=QTIMEOUT)
            except Exception as e:
                return results, f"请求异常：{e}"
            if r.status_code == 401:
                self.invalidate_auth()
                if not self.ensure_login(cfg["username"], cfg["password"]):
                    return results, "登录态失效且重登失败"
                continue
            if r.status_code != 200:
                return results, f"HTTP {r.status_code}"
            try:
                data = r.json()
            except Exception:
                return results, "返回非 JSON（可能未登录或接口变化）"
            if str(data.get("code")) != "1":
                return results, data.get("msg", "查询失败")
            dl = data.get("dataList") or []
            total = int(data.get("totalCount") or 0)
            for it in dl:
                results.extend(self._parse_item(it, teaching_type, cfg["batch"]))
            got += len(dl)
            if not dl or got >= total:
                break
            page += 1
        return results, None

    def query_batches(self, cfg):
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return [], "登录失败，无法获取批次"
        ts = int(time.time() * 1000)
        url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/batch.do?timestamp={ts}"
        try:
            r = self.session.get(url, headers=self._std_headers(), cookies=self._cookies(), timeout=QTIMEOUT)
        except Exception as e:
            return [], f"请求异常：{e}"
        if r.status_code == 401:
            self.invalidate_auth()
            return [], "登录态失效"
        try:
            data = r.json()
        except Exception:
            return [], "返回非 JSON"
        if str(data.get("code")) != "1":
            return [], data.get("msg", "获取批次失败")
        out = []
        fmt = "%Y-%m-%d %H:%M:%S"
        for b in data.get("dataList") or []:
            bt, et, cur = b.get("beginTime"), b.get("endTime"), b.get("currentTime")
            is_open = False
            try:
                is_open = datetime.strptime(bt, fmt) <= datetime.strptime(cur, fmt) <= datetime.strptime(et, fmt)
            except Exception:
                is_open = str(b.get("active")) == "1"
            out.append({"code": b.get("code"), "name": b.get("name"),
                        "beginTime": bt, "endTime": et, "open": is_open,
                        "typeName": b.get("typeName")})
        return out, None

    def query_timetable(self, cfg):
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return None, "登录失败，无法获取课表"
        base = "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/"
        ts = int(time.time() * 1000)
        q = f"?timestamp={ts}&studentCode={cfg['username']}&electiveBatchCode={cfg['batch']}"
        try:
            r = self.session.get(base + "teachingTime.do" + q, headers=self._std_headers(),
                                 cookies=self._cookies(), timeout=QTIMEOUT)
            data = r.json()
        except Exception as e:
            return None, f"请求异常：{e}"
        if str(data.get("code")) != "1":
            return None, data.get("msg", "获取课表失败")
        classes = []
        for it in data.get("dataList") or []:
            try:
                day = int(it.get("dayOfWeek") or 0)
                begin = int(it.get("beginSection") or 0)
                end = int(it.get("endSection") or 0)
            except (TypeError, ValueError):
                continue
            classes.append({"day": day, "begin": begin, "end": end,
                            "name": it.get("courseName") or "",
                            "teacher": it.get("teacherName") or "",
                            "place": it.get("teachingPlace") or "",
                            "weeks": it.get("weekName") or ""})
        no_arr = []
        try:
            r2 = self.session.get(base + "noArranged.do" + q, headers=self._std_headers(),
                                  cookies=self._cookies(), timeout=QTIMEOUT)
            d2 = r2.json()
            if str(d2.get("code")) == "1":
                for it in d2.get("dataList") or []:
                    no_arr.append({"name": it.get("courseName") or "",
                                   "teacher": it.get("teacherName") or "",
                                   "credit": it.get("credit") or ""})
        except Exception:
            pass
        return {"classes": classes, "noArranged": no_arr}, None

    def query_selected(self, cfg):
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return None, "登录失败"
        ts = int(time.time() * 1000)
        url = (f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/courseResult.do"
               f"?timestamp={ts}&studentCode={cfg['username']}&electiveBatchCode={cfg['batch']}")
        try:
            r = self.session.get(url, headers=self._std_headers(), cookies=self._cookies(), timeout=QTIMEOUT)
            if r.status_code == 401:
                self.invalidate_auth()
                if not self.ensure_login(cfg["username"], cfg["password"]):
                    return None, "登录态失效"
                r = self.session.get(url, headers=self._std_headers(), cookies=self._cookies(), timeout=QTIMEOUT)
            data = r.json()
        except Exception as e:
            return None, f"请求异常：{e}"
        if str(data.get("code")) != "1":
            return None, data.get("msg", "查询已选失败")
        out = []
        for it in data.get("dataList") or []:
            out.append({
                "teachingClassID": it.get("teachingClassID"),
                "courseName": it.get("courseName") or "",
                "teacherName": it.get("teacherName") or "",
                "place": it.get("teachingPlace") or "",
                "credit": it.get("credit") or "",
                "typeName": it.get("courseTypeName") or "",
                "campus": it.get("campusName") or "",
                "isConflict": str(it.get("isConflict")),
                "conflictDesc": it.get("conflictDesc") or "",
                "canDelete": str(it.get("canDelete")),
            })
        return out, None

    def withdraw_course(self, cfg, teaching_class_id):
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return False, "登录失败"
        param = {"data": {"operationType": "2", "studentCode": cfg["username"],
                          "electiveBatchCode": cfg["batch"], "teachingClassId": teaching_class_id,
                          "isMajor": "1"}}
        ts = int(time.time() * 1000)
        url = (f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/deleteVolunteer.do"
               f"?timestamp={ts}&deleteParam={requests.utils.quote(json.dumps(param))}")
        try:
            r = self.session.get(url, headers=self._std_headers(), cookies=self._cookies(), timeout=QTIMEOUT)
            if r.status_code == 401:
                self.invalidate_auth()
                if not self.ensure_login(cfg["username"], cfg["password"]):
                    return False, "登录态失效"
                r = self.session.get(url, headers=self._std_headers(), cookies=self._cookies(), timeout=QTIMEOUT)
            data = r.json()
        except Exception as e:
            return False, f"请求异常：{e}"
        return (str(data.get("code")) == "1"), data.get("msg", "")

    def send_success(self, name, email_user, email_auth):
        if not email_user or not email_auth or yagmail is None:
            return
        try:
            yag = yagmail.SMTP(user=email_user, password=email_auth, host="smtp.qq.com", port=465)
            yag.send(to=email_user, subject="选课成功", contents=f"选课成功 - {name}")
            self.log(f"已发送成功提醒邮件到 {email_user}")
        except Exception as e:
            self.log(f"邮件发送失败：{e}")

    def fire_once(self, course, cfg, done_event):
        if self.stop_flag.is_set() or done_event.is_set():
            return
        name = course["name"]
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return
        data = {"data": {"operationType": "1", "studentCode": cfg["username"],
                         "electiveBatchCode": course.get("batch") or cfg["batch"],
                         "teachingClassId": course["id"], "isMajor": "1",
                         "campus": cfg.get("campus", "02"), "teachingClassType": course["type"]}}
        body = "addParam=" + requests.utils.quote(json.dumps(data))
        try:
            resp = self.session.post(
                "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteer.do",
                headers=self._std_headers(), data=body, cookies=self._cookies(), timeout=TIMEOUT)
        except Exception as e:
            self.log(f"[{name}] 错误：{e}")
            return
        if resp.status_code != 200:
            if resp.status_code == 401:
                self.invalidate_auth()
            return
        with self.count_lock:
            self.total_count += 1
            cnt = self.total_count
        self.event("count", cnt)
        try:
            j = resp.json()
        except Exception:
            return
        code = str(j.get("code"))
        msg = j.get("msg", resp.text[:80])
        self.log(f"[{name}] #{cnt} code={code} {msg}")
        if code == "1":
            if not done_event.is_set():
                self.log(f"抢课成功：{name}")
                self.event("status", [name, "已成功"])
                self.send_success(name, cfg["email_user"], cfg["email_auth"])
                done_event.set()
        elif code == "302":
            self.invalidate_auth()

    def wait_until_start(self, start_at):
        if not start_at:
            return
        try:
            target = datetime.strptime(start_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            self.log("定时格式错误，立即开抢")
            return
        while not self.stop_flag.is_set():
            remain = (target - datetime.now()).total_seconds()
            if remain <= 0:
                self.log("到点，开抢！")
                return
            if remain <= 3:
                time.sleep(0.05)
            else:
                self.log(f"距离开抢还有 {timedelta(seconds=int(remain))}")
                time.sleep(min(remain - 2, 5))

    @staticmethod
    def _peak_active(peak):
        if not peak or not peak.get("enabled"):
            return False
        try:
            s = int(peak.get("startMin"))
            e = int(peak.get("endMin"))
            now = datetime.now().minute
            if s <= e:
                return s <= now <= e
            return now >= s or now <= e
        except (TypeError, ValueError):
            return False

    def run(self, cfg):
        self.stop_flag.clear()
        self.total_count = 0
        try:
            self.ensure_session()
            if cfg["mode"] == "custom":
                base_salvo = max(1, int(float(cfg.get("custom_salvo", 1))))
                base_interval = max(0.0, float(cfg.get("custom_interval", 0.5)))
            else:
                m = MODES[cfg["mode"]]
                base_salvo, base_interval = m["salvo"], m["interval"]
            peak = cfg.get("peak") or {}
            try:
                mult = float(peak.get("mult", 4))
                if mult < 1:
                    mult = 1.0
            except (TypeError, ValueError):
                mult = 4.0
            peak_on = bool(peak.get("enabled"))
            max_salvo = base_salvo
            if peak_on and base_interval == 0:
                max_salvo = max(base_salvo, int(base_salvo * mult) + 1)

            courses = cfg["courses"]
            self.log(f"模式：{cfg['mode']}（间隔 {base_interval:g} 秒，每轮每门课 ×{base_salvo} 请求） 课程数={len(courses)}")
            if peak_on:
                self.log(f"高峰增强：每小时第 {peak.get('startMin')}~{peak.get('endMin')} 分 强度×{mult:g}（优先缩短间隔）")
            if not self.ensure_login(cfg["username"], cfg["password"]):
                self.log("登录失败，无法开始")
                return
            try:
                self.session.get("https://xk.ynu.edu.cn/", timeout=TIMEOUT)
            except Exception:
                pass
            self.wait_until_start(cfg.get("start_at", ""))
            if self.stop_flag.is_set():
                return
            done = {id(c): threading.Event() for c in courses}
            for c in courses:
                self.event("status", [c["name"], "抢课中…"])
            pool = ThreadPoolExecutor(max_workers=max(4, len(courses) * max_salvo + 2))
            was_peak = False
            err_streak = 0
            try:
                while not self.stop_flag.is_set():
                    # 单轮整体兜底：长期挂机时任何偶发异常都不能让抢课循环退出
                    try:
                        active = [c for c in courses if not done[id(c)].is_set()]
                        if not active:
                            self.log("所有课程均已抢到，结束。")
                            break
                        in_peak = self._peak_active(peak)
                        if in_peak and not was_peak:
                            self.log(f"进入高峰时段，强度×{mult:g}")
                        elif was_peak and not in_peak:
                            self.log("离开高峰时段，恢复正常强度")
                        was_peak = in_peak
                        if in_peak:
                            if base_interval > 0:
                                cur_salvo, cur_interval = base_salvo, base_interval / mult
                            else:
                                cur_salvo, cur_interval = max(1, int(round(base_salvo * mult))), 0.0
                        else:
                            cur_salvo, cur_interval = base_salvo, base_interval

                        futures = []
                        for c in active:
                            for _ in range(cur_salvo):
                                futures.append(pool.submit(self.fire_once, c, cfg, done[id(c)]))
                        for f in futures:
                            try:
                                f.result(timeout=TIMEOUT + 5)
                            except Exception:
                                pass
                        err_streak = 0
                        if self.stop_flag.is_set():
                            break
                        if cur_interval:
                            time.sleep(cur_interval)
                    except Exception as e:
                        err_streak += 1
                        self.log(f"本轮异常（第 {err_streak} 次，已自动继续）：{e}")
                        time.sleep(min(5.0, 0.5 * err_streak))
            finally:
                pool.shutdown(wait=False)
        except Exception as e:
            self.log(f"运行异常：{e}")
        finally:
            self.event("finished", None)

    def stop(self):
        self.stop_flag.set()


# ============================ 配置 / 日志 / 命令行 ============================
def setup_logging(logfile):
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    if logfile:
        try:
            fh = RotatingFileHandler(logfile, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)
        except Exception as e:
            log.warning(f"日志文件无法写入（{e}），仅输出到屏幕")


def load_cfg(path):
    if not os.path.exists(path):
        log.error(f"找不到配置文件：{path}（可复制 config.example.json 为 config.json）")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 补全缺省字段，避免引擎里 KeyError
    cfg.setdefault("campus", "02")
    cfg.setdefault("mode", "fast")
    cfg.setdefault("custom_salvo", "1")
    cfg.setdefault("custom_interval", "0.5")
    cfg.setdefault("start_at", "")
    cfg.setdefault("email_user", "")
    cfg.setdefault("email_auth", "")
    cfg.setdefault("peak", {"enabled": False, "startMin": "43", "endMin": "45", "mult": "4"})
    cfg.setdefault("courses", [])
    if not cfg.get("batch"):
        cfg["batch"] = DEFAULT_BATCH
    return cfg


def make_engine():
    def _event(kind, payload):
        if kind == "status":
            name, st = payload
            log.info(f"[状态] {name} -> {st}")
        elif kind == "finished":
            log.info("抢课已结束。")
        # count 忽略：每条请求日志已带 # 计数
    if requests is None or ddddocr is None:
        log.error("缺少依赖：请先 pip install requests ddddocr（服务器用 opencv-python-headless）")
        sys.exit(3)
    return GrabEngine(log.info, _event)


def cmd_run(cfg, args):
    for k in ("username", "password"):
        if not cfg.get(k):
            log.error(f"配置缺少必填项：{k}")
            sys.exit(2)
    if not cfg.get("courses"):
        log.error("配置里 courses 为空，先用 query 子命令查到 教学班ID/type 再填进去")
        sys.exit(2)
    eng = make_engine()

    def _sig(signum, frame):
        log.info(f"收到信号 {signum}，正在停止抢课…")
        eng.stop()
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    t = threading.Thread(target=eng.run, args=(cfg,), daemon=True)
    t.start()
    while t.is_alive():
        t.join(0.5)
    log.info("进程退出。")


def cmd_query(cfg, args):
    idx = args.category
    if idx < 0 or idx >= len(QUERY_CATS):
        log.error(f"分类序号需在 0~{len(QUERY_CATS)-1}")
        _print_cats()
        sys.exit(2)
    name, endpoint, ttype = QUERY_CATS[idx]
    eng = make_engine()
    log.info(f"查询 [{name}] 关键词='{args.keyword or '全部'}' …")
    results, err = eng.query_courses(cfg, endpoint, ttype, args.keyword or "")
    if err:
        log.error(f"查询失败：{err}")
        sys.exit(1)
    if not results:
        log.info("没有查到课程。")
        return
    print(f"\n共 {len(results)} 个教学班（type={ttype}）：\n")
    print(f"{'余量':>4}  {'满/冲突':<7} {'教学班ID':<34} 课程 / 教师 / 地点")
    print("-" * 100)
    for r in results:
        rm = "-" if r["remain"] is None else str(r["remain"])
        flag = []
        if r["isFull"] == "1":
            flag.append("满")
        if r["isConflict"] == "1":
            flag.append("冲突")
        fl = "/".join(flag) if flag else "可选"
        print(f"{rm:>4}  {fl:<7} {str(r['teachingClassID']):<34} "
              f"{r['courseName']} / {r['teacherName']} / {r['place']}")
    print("\n提示：把某门课加入 config.json 的 courses，格式："
          f'{{"name": "课程名", "id": "上面的教学班ID", "type": "{ttype}"}}\n')


def cmd_batches(cfg, args):
    eng = make_engine()
    log.info("获取选课批次 …")
    batches, err = eng.query_batches(cfg)
    if err:
        log.error(f"获取批次失败：{err}")
        sys.exit(1)
    print(f"\n共 {len(batches)} 个批次（★=当前开放）：\n")
    for b in batches:
        star = "★" if b["open"] else " "
        print(f"{star} code={b['code']}")
        print(f"    {b['name']}  [{b.get('typeName') or ''}]  {b['beginTime']} ~ {b['endTime']}")
    print("\n提示：把开放批次的 code 填到 config.json 的 batch 字段。\n")


def cmd_selected(cfg, args):
    eng = make_engine()
    log.info("获取已选课程 …")
    sel, err = eng.query_selected(cfg)
    if err:
        log.error(f"获取失败：{err}")
        sys.exit(1)
    if not sel:
        log.info("当前没有已选课程。")
        return
    total_credit = 0.0
    print(f"\n已选 {len(sel)} 门：\n")
    for s in sel:
        try:
            total_credit += float(s["credit"] or 0)
        except ValueError:
            pass
        cflag = "  [冲突]" if s["isConflict"] == "1" else ""
        dflag = "" if s["canDelete"] == "1" else "  (不可退)"
        print(f"  {s['teachingClassID']:<34} {s['courseName']} / {s['teacherName']} "
              f"/ {s['credit']}学分 / {s['typeName']}{cflag}{dflag}")
    print(f"\n合计 {total_credit:g} 学分。退选：python qiangke_cli.py withdraw <教学班ID>\n")


def cmd_timetable(cfg, args):
    eng = make_engine()
    log.info("获取我的课表 …")
    data, err = eng.query_timetable(cfg)
    if err:
        log.error(f"获取失败：{err}")
        sys.exit(1)
    days = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    print(f"\n有安排的课（{len(data['classes'])} 节）：\n")
    for c in sorted(data["classes"], key=lambda x: (x["day"], x["begin"])):
        d = days[c["day"]] if 0 < c["day"] < len(days) else f"周{c['day']}"
        print(f"  {d} 第{c['begin']}-{c['end']}节  {c['name']} / {c['teacher']} / {c['place']}  {c['weeks']}")
    if data["noArranged"]:
        print(f"\n未排时间（{len(data['noArranged'])} 门）：")
        for n in data["noArranged"]:
            print(f"  {n['name']} / {n['teacher']} / {n['credit']}学分")
    print()


def cmd_withdraw(cfg, args):
    eng = make_engine()
    log.info(f"退选 {args.tcid} …")
    ok, msg = eng.withdraw_course(cfg, args.tcid)
    log.info(("退选成功：" if ok else "退选失败：") + (msg or ""))
    sys.exit(0 if ok else 1)


def _print_cats():
    print("分类序号：")
    for i, (nm, _, tt) in enumerate(QUERY_CATS):
        print(f"  {i} = {nm}")


def main():
    ap = argparse.ArgumentParser(description="YNU 抢课助手 · Linux 无界面版")
    ap.add_argument("-c", "--config", default="config.json", help="配置文件路径（默认 config.json）")
    ap.add_argument("--log", default="qiangke.log", help="日志文件（默认 qiangke.log，设为空字符串则不写文件）")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("run", help="按配置开始抢课（长期挂机）")
    p_q = sub.add_parser("query", help="查课，拿到 教学班ID/type")
    p_q.add_argument("category", type=int, help="分类序号 0~4（0=通识选修 1=推荐 2=主修 3=体育 4=创新创业）")
    p_q.add_argument("keyword", nargs="?", default="", help="课程名关键词（可省略=全部）")
    sub.add_parser("batches", help="列出选课批次，拿到 batch 码")
    sub.add_parser("selected", help="查看已选课程")
    sub.add_parser("timetable", help="查看我的课表")
    p_w = sub.add_parser("withdraw", help="退选一门课")
    p_w.add_argument("tcid", help="教学班ID")

    args = ap.parse_args()
    setup_logging(args.log)
    if not args.cmd:
        ap.print_help()
        print()
        _print_cats()
        return
    cfg = load_cfg(args.config)
    {"run": cmd_run, "query": cmd_query, "batches": cmd_batches,
     "selected": cmd_selected, "timetable": cmd_timetable,
     "withdraw": cmd_withdraw}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
