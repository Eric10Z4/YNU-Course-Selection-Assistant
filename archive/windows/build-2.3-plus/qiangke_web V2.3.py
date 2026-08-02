# -*- coding: utf-8 -*-
"""
YNU 抢课助手 · PyWebView 版（毛玻璃界面）
=======================================
· 界面用 HTML/CSS/JS（真·毛玻璃 backdrop-filter + 背景图 + 高清渲染）
· 后端复用抢课引擎：登录/验证码OCR/齐射并发/查课/自动重登
· 分级模式 turbo/fast/steady/custom；下拉定时；配置保存加载；实时日志
依赖： pip install pywebview requests onnxruntime yagmail pillow
背景图：把图片命名为 background.png（或 .jpg）放到 exe 同目录即可；不放则用暗色渐变。
"""

import os
import sys
import json
import time
import queue
import secrets
import threading
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urlencode

try:
    import webview
except Exception:
    webview = None
try:
    import requests
except Exception:
    requests = None
try:
    import numpy as np
    from PIL import Image as _PILImage
    import io as _io
    import onnxruntime as _ort

    # ---- 内嵌轻量 OCR（替代 ddddocr）----
    class _LiteOCR:
        _charset = None
        _session = None

        @staticmethod
        def _res(name):
            if getattr(sys, 'frozen', False):
                return os.path.join(sys._MEIPASS, name)
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)

        @classmethod
        def _load(cls):
            if cls._session is not None:
                return
            with open(cls._res("ocr_charset.json"), "r", encoding="utf-8") as f:
                cls._charset = json.load(f)
            cls._session = _ort.InferenceSession(
                cls._res("ocr_model.onnx"),
                providers=["CPUExecutionProvider"])

        @classmethod
        def classification(cls, img_bytes):
            cls._load()
            im = _PILImage.open(_io.BytesIO(img_bytes))
            if im.mode == "RGBA":
                bg = _PILImage.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3])
                im = bg
            w, h = im.size
            new_w = int(w * (64 / h))
            im = im.resize((new_w, 64), _PILImage.BILINEAR)
            im = im.convert("L")
            arr = np.array(im).astype(np.float32) / 255.0
            arr = arr[np.newaxis, np.newaxis, :, :]
            output = cls._session.run(None, {"input1": arr})[0]
            pred = np.argmax(output[:, 0, :], axis=1)
            result = []
            prev = -1
            for idx in pred:
                idx = int(idx)
                if idx != 0 and idx != prev and idx < len(cls._charset):
                    result.append(cls._charset[idx])
                prev = idx
            return "".join(result)

    lite_ocr = _LiteOCR()
except Exception as _ocr_err:
    lite_ocr = None
    _ocr_init_error = str(_ocr_err)
else:
    _ocr_init_error = ""
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
try:
    from PIL import Image
except Exception:
    Image = None
import base64
import io

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
BG_CANDIDATES = ("background.png", "background.jpg", "background.jpeg", "bg.png", "bg.jpg")

# ---- 本地服务器 / 消息广播（取代不稳定的 pywebview js_api 桥接）----
TOKEN = ""                       # 启动时随机生成，前端与服务器共享，防止本机其它程序访问
_subs = []                       # 每个 SSE 连接一个队列
_backlog = deque(maxlen=2000)    # 最近消息的环形缓冲，用于断线重连后补发
_eid = 0                         # 单调递增的消息 ID
_lock = threading.Lock()         # 同时保护 _subs / _backlog / _eid


def _emit(msg):
    """给每条消息编号、存入环形缓冲，并广播给所有已连接的 SSE 客户端。

    结果/状态类推送若恰好在 SSE 短暂重连时发出，浏览器重连会带上 Last-Event-ID，
    服务器据此补发这段时间漏掉的消息，避免界面“查了没反应”。
    """
    global _eid
    data = json.dumps(msg, ensure_ascii=False)
    with _lock:
        _eid += 1
        item = (_eid, data)
        _backlog.append(item)
        for q in list(_subs):
            try:
                q.put_nowait(item)
            except Exception:
                pass


def keep_awake(on):
    """挂机期间阻止 Windows 进入睡眠/休眠（否则定时/高峰抢课会被系统睡眠打断）。
    只在抢课/等待开始期间开启，停止后恢复，空闲时电脑照常正常休眠。
    注意：这挡不住“合上笔记本盖子”触发的睡眠——长期挂机建议插电、且把合盖动作设为“不采取操作”。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        if on:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


def resource_path(name):
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, name))
    try:
        cands.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), name))
    except Exception:
        pass
    cands.append(os.path.join(os.getcwd(), name))
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None


# ============================ 抢课引擎（与界面无关，可复用） ============================
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
        return lite_ocr

    def login(self, username, password):
        try:
            ts = int(time.time() * 1000)
            url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/4/vcode.do?timestamp={ts}"
            r = self.session.get(url, headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://xk.ynu.edu.cn/", "X-Requested-With": "XMLHttpRequest"}, timeout=TIMEOUT)
            vtoken = r.json()["data"]["token"]
            url = "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/vcode/image.do?" + urlencode({"vtoken": vtoken})
            r = self.session.get(url, headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://xk.ynu.edu.cn/", "X-Requested-With": "XMLHttpRequest"}, timeout=TIMEOUT)
            code = self.get_ocr().classification(r.content)
            ts = int(time.time() * 1000)
            login_qs = urlencode({"timestrap": ts, "loginName": username,
                                  "loginPwd": password, "verifyCode": code, "vtoken": vtoken})
            url = f"https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/student/check/login.do?{login_qs}"
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
        self.ensure_session()   # 任何触发登录的入口（查询/批次/抢课）都先确保会话存在
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
            cap = tc.get("classCapacity") if tc.get("classCapacity") is not None else item.get("classCapacity")
            sel = tc.get("numberOfSelected") if tc.get("numberOfSelected") is not None else item.get("numberOfSelected")
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
        """拉取选课批次列表；用 currentTime 与起止时间判断是否正在开放。"""
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
        """获取我的课表（teachingTime.do）+ 未安排时间课程（noArranged.do）。"""
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return None, "登录失败，无法获取课表"
        base = "https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/"
        ts = int(time.time() * 1000)
        q = "?" + urlencode({"timestamp": ts, "studentCode": cfg['username'],
                             "electiveBatchCode": cfg['batch']})
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
        """查询已选课程（courseResult.do）。返回 (list, err)。"""
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return None, "登录失败"
        ts = int(time.time() * 1000)
        url = ("https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/courseResult.do?"
               + urlencode({"timestamp": ts, "studentCode": cfg['username'],
                            "electiveBatchCode": cfg['batch']}))
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
        """退选（deleteVolunteer.do）。返回 (ok, msg)。"""
        if not self.ensure_login(cfg["username"], cfg["password"]):
            return False, "登录失败"
        param = {"data": {"operationType": "2", "studentCode": cfg["username"],
                          "electiveBatchCode": cfg["batch"], "teachingClassId": teaching_class_id,
                          "isMajor": "1"}}
        ts = int(time.time() * 1000)
        url = ("https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/deleteVolunteer.do?"
               + urlencode({"timestamp": ts,
                            "deleteParam": json.dumps(param)}))
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
        """当前是否在高峰分钟窗内（每小时循环：第 startMin~endMin 分，支持跨小时如 58~02）。"""
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
        keep_awake(True)          # 挂机期间阻止系统睡眠，停止时在 finally 里恢复
        try:
            self.ensure_session()
            if cfg["mode"] == "custom":
                base_salvo = max(1, int(float(cfg.get("custom_salvo", 1))))
                base_interval = max(0.0, float(cfg.get("custom_interval", 0.5)))
            else:
                m = MODES.get(cfg["mode"])
                if m is None:
                    self.log(f"未知模式 '{cfg['mode']}'，已降级为 fast")
                    m = MODES["fast"]
                base_salvo, base_interval = m["salvo"], m["interval"]
            # 高峰增强参数
            peak = cfg.get("peak") or {}
            try:
                mult = float(peak.get("mult", 4))
                if mult < 1:
                    mult = 1.0
            except (TypeError, ValueError):
                mult = 4.0
            peak_on = bool(peak.get("enabled"))
            # 线程池按可能出现的最大并发规模来建（高峰若提升并发，需要更多线程）
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
                        # 计算本轮强度：高峰内优先缩短间隔，间隔已为0则提升并发
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
                        # 不退出循环：记一笔、退避一下再继续（连续出错时退避加长，避免刷屏/空转）
                        err_streak += 1
                        self.log(f"本轮异常（第 {err_streak} 次，已自动继续）：{e}")
                        time.sleep(min(5.0, 0.5 * err_streak))
            finally:
                pool.shutdown(wait=False)
        except Exception as e:
            self.log(f"运行异常：{e}")
        finally:
            keep_awake(False)     # 恢复系统正常睡眠策略
            self.event("finished", None)

    def stop(self):
        self.stop_flag.set()


# ============================ PyWebView 后端 API ============================
class Api:
    def __init__(self):
        self.window = None
        self.engine = GrabEngine(self._log, self._event)
        self.run_thread = None

    # ---- 主动推给前端（通过 SSE 广播，不再依赖 pywebview 桥接）----
    def _log(self, text):
        stamp = f"{datetime.now():%H:%M:%S}  {text}"
        _emit({"t": "log", "text": stamp})

    def _event(self, kind, payload):
        _emit({"t": "event", "kind": kind, "payload": payload})

    def _push(self, fn, payload):
        _emit({"t": "push", "fn": fn, "payload": payload})

    # ---- 前端可调用 ----
    def start(self, cfg):
        if requests is None or lite_ocr is None:
            return {"ok": False, "msg": f"缺少依赖：{_ocr_init_error or 'pip install requests onnxruntime'}"}
        if not cfg.get("username") or not cfg.get("password"):
            return {"ok": False, "msg": "请填写学号和密码"}
        if not cfg.get("courses"):
            return {"ok": False, "msg": "请至少添加一门课程"}
        self.run_thread = threading.Thread(target=self.engine.run, args=(cfg,), daemon=True)
        self.run_thread.start()
        return {"ok": True}

    def stop(self):
        self.engine.stop()
        self._log("正在停止…")
        return {"ok": True}

    def query(self, cfg, cat_index, keyword):
        """后台线程执行，结果通过 onQueryResult 回调推给前端，日志实时可见。"""
        if requests is None or lite_ocr is None:
            self._push("onQueryResult", {"error": f"缺少依赖：{_ocr_init_error or 'requests/onnxruntime 未安装'}"})
            return {"ok": True}
        try:
            cat_index = int(cat_index)
        except Exception:
            cat_index = 0
        if cat_index < 0 or cat_index >= len(QUERY_CATS):
            cat_index = 0

        def worker():
            _, endpoint, ttype = QUERY_CATS[cat_index]
            self._log(f"查询 {QUERY_CATS[cat_index][0]} 关键词='{keyword or '全部'}' …")
            results, err = self.engine.query_courses(cfg, endpoint, ttype, keyword or "")
            if err:
                self._log(f"查询失败：{err}")
                self._push("onQueryResult", {"error": err})
            else:
                # 顺带取一次已选，用于在结果里标记「已选」
                sel, serr = self.engine.query_selected(cfg)
                ids = [s["teachingClassID"] for s in sel] if (not serr and sel) else []
                self._log(f"查询到 {len(results)} 个教学班（已选 {len(ids)} 门）")
                self._push("onQueryResult", {"results": results, "selectedIds": ids})
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def get_selected(self, cfg):
        if requests is None or lite_ocr is None:
            self._push("onSelected", {"error": f"缺少依赖：{_ocr_init_error or 'requests/onnxruntime 未安装'}"})
            return {"ok": True}
        if not cfg.get("username") or not cfg.get("password") or not cfg.get("batch"):
            self._push("onSelected", {"error": "请先填学号密码并选择批次"})
            return {"ok": True}

        def worker():
            self._log("正在获取已选课程…")
            sel, err = self.engine.query_selected(cfg)
            if err:
                self._log(f"获取已选失败：{err}")
                self._push("onSelected", {"error": err})
            else:
                self._log(f"已选课程 {len(sel)} 门")
                self._push("onSelected", {"selected": sel})
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def withdraw(self, cfg, tcid):
        if requests is None or lite_ocr is None:
            return {"ok": False, "msg": "缺少依赖"}

        def worker():
            ok, msg = self.engine.withdraw_course(cfg, tcid)
            self._log(("退选成功：" if ok else "退选失败：") + (msg or ""))
            # 退选后刷新已选列表
            sel, err = self.engine.query_selected(cfg)
            if not err and sel is not None:
                self._push("onSelected", {"selected": sel})
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def get_batches(self, cfg):
        """后台线程执行，结果通过 onBatches 回调推给前端。"""
        if requests is None or lite_ocr is None:
            self._push("onBatches", {"error": f"缺少依赖：{_ocr_init_error or 'requests/onnxruntime 未安装'}"})
            return {"ok": True}
        if not cfg.get("username") or not cfg.get("password"):
            self._push("onBatches", {"error": "请先填写学号和密码"})
            return {"ok": True}

        def worker():
            self._log("正在登录并获取选课批次…")
            batches, err = self.engine.query_batches(cfg)
            if err:
                self._log(f"获取批次失败：{err}")
                self._push("onBatches", {"error": err})
            else:
                self._log(f"已获取 {len(batches)} 个选课批次")
                self._push("onBatches", {"batches": batches})
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def get_timetable(self, cfg):
        if requests is None or lite_ocr is None:
            self._push("onTimetable", {"error": f"缺少依赖：{_ocr_init_error or 'requests/onnxruntime 未安装'}"})
            return {"ok": True}
        if not cfg.get("username") or not cfg.get("password"):
            self._push("onTimetable", {"error": "请先填写学号和密码"})
            return {"ok": True}
        if not cfg.get("batch"):
            self._push("onTimetable", {"error": "请先选择/获取选课批次"})
            return {"ok": True}

        def worker():
            self._log("正在获取我的课表…")
            data, err = self.engine.query_timetable(cfg)
            if err:
                self._log(f"获取课表失败：{err}")
                self._push("onTimetable", {"error": err})
            else:
                self._log(f"课表：{len(data['classes'])} 节有安排，{len(data['noArranged'])} 门未排时间")
                self._push("onTimetable", data)
        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def save_config(self, cfg):
        try:
            path = None
            try:
                path = self.window.create_file_dialog(
                    webview.SAVE_DIALOG, save_filename="qiangke_config.json",
                    file_types=("JSON (*.json)",))
            except Exception:
                path = None
            if isinstance(path, (list, tuple)):
                path = path[0] if path else None
            if not path:
                path = os.path.join(os.getcwd(), "qiangke_config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._log(f"已保存配置：{path}")
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "msg": str(e)}

    def load_config(self):
        try:
            path = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=("JSON (*.json)",))
            if isinstance(path, (list, tuple)):
                path = path[0] if path else None
            if not path:
                return {"ok": False}
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._log(f"已加载配置：{path}")
            return {"ok": True, "cfg": cfg}
        except Exception as e:
            return {"ok": False, "msg": str(e)}


# ============================ 背景图 / HTML ============================
def _bg_rule():
    """返回 #bg 的 background/filter CSS：有图用图，没图用暗色渐变。"""
    if Image is not None:
        p = None
        for n in BG_CANDIDATES:
            p = resource_path(n)
            if p:
                break
        if p:
            try:
                im = Image.open(p).convert("RGB")
                im.thumbnail((1920, 1920), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=82)
                b64 = base64.b64encode(buf.getvalue()).decode()
                return (f'background:#0d0d13 url("data:image/jpeg;base64,{b64}") center/cover no-repeat;'
                        f'filter:brightness(.62) saturate(1.05);')
            except Exception:
                pass
    return ('background:radial-gradient(1200px 600px at 78% 8%, rgba(124,108,245,.30), transparent 55%),'
            'radial-gradient(900px 500px at 10% 100%, rgba(52,211,153,.12), transparent 50%),'
            'linear-gradient(160deg,#141327,#0b0b12 70%);')


# 课表弹窗可选专属背景图：schedule_bg.png / bg2.png 等；没放则用暗色蒙层（透出并模糊主界面）
SCHED_BG_CANDIDATES = ("schedule_bg.png", "schedule_bg.jpg", "schedule.png", "bg2.png", "bg2.jpg")


def _bg2_rule():
    if Image is not None:
        p = None
        for n in SCHED_BG_CANDIDATES:
            p = resource_path(n)
            if p:
                break
        if p:
            try:
                im = Image.open(p).convert("RGB")
                im.thumbnail((1920, 1920), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=82)
                b64 = base64.b64encode(buf.getvalue()).decode()
                return (f'background:#0d0d13 url("data:image/jpeg;base64,{b64}") center/cover no-repeat;'
                        f'filter:brightness(.5) saturate(1.05);')
            except Exception:
                pass
    return ('background:rgba(8,8,14,.82);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);')


def build_html():
    return (HTML.replace("__BG_RULE__", _bg_rule())
                .replace("__BG2_RULE__", _bg2_rule())
                .replace("__BATCH__", DEFAULT_BATCH)
                .replace("__TOKEN__", TOKEN))


# ============================ 本地 HTTP 服务器 ============================
# 只监听 127.0.0.1（本机），/api 与 /events 需带正确 TOKEN 才受理。
_ALLOWED = {"start", "stop", "query", "get_selected", "withdraw",
            "get_batches", "get_timetable", "save_config", "load_config"}
_API = None          # 在 main() 中赋值为 Api 实例


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):        # 静音，避免控制台刷屏
        pass

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, build_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if u.path == "/favicon.ico":       # 浏览器自动请求，无图标，静默 204
            self._send(204)
            return
        if parse_qs(u.query).get("t", [""])[0] != TOKEN:
            self._send(403); return
        if u.path == "/events":
            # 重连时浏览器自动带上 Last-Event-ID；据此补发断线期间漏掉的消息
            try:
                last = int(self.headers.get("Last-Event-ID") or 0)
            except Exception:
                last = 0
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = queue.Queue(maxsize=4000)
            # 在同一把锁内“快照待补发消息 + 登记订阅”，保证不漏发也不重发
            with _lock:
                replay = [it for it in _backlog if it[0] > last] if last else []
                _subs.append(q)
            try:
                self.wfile.write(b": connected\n\n")
                for eid, data in replay:
                    self.wfile.write(("id: %d\ndata: %s\n\n" % (eid, data)).encode("utf-8"))
                self.wfile.flush()
                while True:
                    try:
                        eid, data = q.get(timeout=15)
                        self.wfile.write(("id: %d\ndata: %s\n\n" % (eid, data)).encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")   # 心跳，探测断线
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with _lock:
                    if q in _subs:
                        _subs.remove(q)
            return
        self._send(404)

    def do_POST(self):
        u = urlparse(self.path)
        if parse_qs(u.query).get("t", [""])[0] != TOKEN:
            self._json(403, {"error": "forbidden"}); return
        if not u.path.startswith("/api/"):
            self._json(404, {"error": "not found"}); return
        name = u.path[len("/api/"):]
        if name not in _ALLOWED or _API is None:
            self._json(400, {"error": "unknown method"}); return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length else b"[]"
        try:
            args = json.loads(raw.decode("utf-8") or "[]")
            if not isinstance(args, list):
                args = [args]
        except Exception:
            args = []
        try:
            result = getattr(_API, name)(*args)
        except Exception as e:
            self._json(500, {"error": str(e)}); return
        self._json(200, result if result is not None else {"ok": True})


def start_server():
    """在本机随机端口上启动服务器，返回 (server, port)。"""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


HTML = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --text:#eef0f8; --sub:#9a9ab6; --accent:#7c6cf5; --accent2:#a89bff;
  --green:#34d399; --red:#fb7185; --amber:#fbbf24;
  --panel:rgba(22,22,32,.10); --panel2:rgba(34,34,50,.15);
  --field:rgba(8,8,16,.20); --border:rgba(255,255,255,.14); --border2:rgba(255,255,255,.20);
  --noise:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.045'/%3E%3C/svg%3E");
}
*{box-sizing:border-box;margin:0;padding:0;font-family:"Microsoft YaHei UI","Segoe UI",system-ui,sans-serif}
html,body{height:100%}
#bg{position:fixed;inset:0;z-index:-2;__BG_RULE__}
body{color:var(--text);overflow:hidden;user-select:none}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.16);border-radius:6px}
::-webkit-scrollbar-track{background:transparent}
.app{display:flex;flex-direction:column;height:100vh;padding:16px;gap:12px;text-shadow:0 1px 2px rgba(0,0,0,.5)}
input,select,textarea{text-shadow:none}
.head{display:flex;align-items:center;flex:none}
.head h1{font-size:19px;font-weight:800;letter-spacing:.5px}
.head .status{margin-left:auto;font-size:13px;font-weight:700;color:var(--sub)}
.head .status.run{color:var(--green)}
.body{display:flex;gap:14px;flex:1;min-height:0}
.left{width:360px;flex:none;display:flex;flex-direction:column;gap:12px;overflow:auto;padding-right:2px}
.right{flex:1;display:flex;flex-direction:column;gap:12px;min-width:0}
.card{background:var(--noise),var(--panel);backdrop-filter:blur(0px) saturate(1.6);-webkit-backdrop-filter:blur(0px) saturate(1.6);
  border:1px solid var(--border);border-radius:16px;padding:14px 16px;box-shadow:0 8px 30px rgba(0,0,0,.30)}
.sec{display:flex;align-items:center;gap:9px;margin-bottom:10px}
.sec .bar{width:4px;height:16px;background:linear-gradient(var(--accent2),var(--accent));border-radius:2px}
.sec b{font-size:13px}
.row{display:flex;align-items:center;gap:10px;margin:8px 0}
.row label{width:78px;font-size:13px;color:var(--text);flex:none}
input,select{background:var(--field);border:1px solid var(--border);border-radius:9px;color:var(--text);
  font-size:13px;padding:8px 10px;outline:none;transition:border-color .15s;width:100%}
input:focus,select:focus{border-color:var(--accent)}
input.bad{border-color:var(--red);background:rgba(120,30,50,.25)}
select option{background:#16161f}
.mode{display:flex;align-items:center;gap:9px;padding:6px 4px;border-radius:8px;cursor:pointer;font-size:13px}
.mode:hover{background:rgba(255,255,255,.04)}
.mode .rd{width:15px;height:15px;border-radius:50%;border:2px solid #565676;flex:none}
.mode.on .rd{border-color:var(--accent);box-shadow:inset 0 0 0 3px var(--accent)}
.mode .nm{font-weight:700;width:58px}
.mode.on .nm{color:var(--accent2)}
.mode .iv{color:var(--amber);font-family:Consolas,monospace;font-weight:700;font-size:12px}
.mode .wk{color:var(--sub);font-size:12px}
.mode .mini{width:44px;text-align:center;padding:4px 4px}
.desc{color:var(--sub);font-size:12px;margin-top:6px;min-height:16px}
.tip{color:var(--sub);font-size:12px;line-height:1.45}
.hint{color:var(--red);font-size:12px;margin-top:4px;min-height:15px}
.btns{display:flex;gap:8px}
.ghost{flex:1;background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:9px;
  padding:9px;font-size:12.5px;cursor:pointer;transition:.15s}
.ghost:hover{border-color:var(--border2);background:rgba(255,255,255,.06)}
.tabs{display:flex;gap:6px;flex:none}
.tab{padding:9px 18px;font-size:13px;font-weight:700;color:var(--sub);cursor:pointer;border-radius:11px 11px 0 0}
.tab.on{color:var(--accent2);background:var(--panel)}
.pane{flex:1;min-height:0;display:none;flex-direction:column}
.pane.on{display:flex}
.qbar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.qbar select{width:auto;min-width:150px}
.qbar input{width:150px}
.btn{background:linear-gradient(135deg,var(--accent2),var(--accent));border:none;color:#fff;border-radius:9px;
  padding:9px 15px;font-size:12.5px;font-weight:700;cursor:pointer}
.btn:hover{filter:brightness(1.08)}
.chk{display:flex;align-items:center;gap:6px;color:var(--sub);font-size:12px;cursor:pointer}
.tablewrap{flex:1;min-height:0;overflow:auto;border:1px solid var(--border);border-radius:12px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
thead th{position:sticky;top:0;background:rgba(20,20,30,.92);backdrop-filter:blur(6px);color:var(--sub);
  text-align:left;padding:10px;font-weight:700;z-index:1}
tbody td{padding:8px 10px;border-top:1px solid rgba(255,255,255,.06)}
tbody tr:hover{background:rgba(255,255,255,.04)}
.ok{color:var(--green)}
.full{color:var(--red)}
.tag{font-size:11px;padding:1px 7px;border-radius:6px;background:rgba(255,255,255,.08);white-space:nowrap}
.tag.clk{cursor:help;background:rgba(251,113,133,.18);color:#fecdd3}
.tag.sel{background:rgba(52,211,153,.22);color:#a7f3d0}
.act{display:flex;align-items:center;gap:10px;margin-top:10px}
.act .tip{color:var(--sub);font-size:12px}
.del{color:var(--red);cursor:pointer;font-weight:700}
.addrow{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.addrow input{width:auto;flex:1;min-width:70px}
.addrow input.wid{flex:2}
.addrow select{width:auto}
.log{flex:none;height:170px;display:flex;flex-direction:column}
.log.big{position:fixed;inset:16px;height:auto;z-index:60;
  background:rgba(13,13,20,.97);backdrop-filter:blur(30px);box-shadow:0 20px 70px rgba(0,0,0,.6)}
.log.big .logbox{font-size:13.5px;line-height:1.6}
.logtop{display:flex;align-items:center;gap:9px;margin-bottom:6px}
.logtop b{font-size:13px}
.cnt{margin-left:auto;color:var(--accent2);font-weight:700;font-size:12px}
.logbox{flex:1;overflow:auto;background:rgba(6,6,12,.55);border:1px solid var(--border);border-radius:12px;
  padding:10px;font-family:Consolas,monospace;font-size:12px;color:#d3d3e6;white-space:pre-wrap;line-height:1.5}
.foot{display:flex;gap:12px;flex:none}
.go,.stop{flex:1;border:none;border-radius:12px;padding:14px;font-size:15px;font-weight:800;cursor:pointer}
.go{background:linear-gradient(135deg,#4ade80,#22c55e);color:#04140b}
.go:disabled{background:rgba(255,255,255,.08);color:var(--sub);cursor:not-allowed}
.stop{background:rgba(255,255,255,.08);color:var(--red)}
.stop:hover:not(:disabled){background:var(--red);color:#fff}
.stop:disabled{color:rgba(255,255,255,.25);cursor:not-allowed}
/* 课表弹窗 */
.modal{position:fixed;inset:0;z-index:80;display:none;align-items:center;justify-content:center;padding:24px}
.modal.on{display:flex}
.modal-bg{position:absolute;inset:0;z-index:-1;__BG2_RULE__}
.modal-card{width:min(1040px,96vw);max-height:92vh;overflow:auto;position:relative;
  background:var(--noise),rgba(20,20,30,.30);backdrop-filter:blur(0px) saturate(1.6);-webkit-backdrop-filter:blur(0px);
  border:1px solid var(--border);border-radius:18px;padding:18px 20px;box-shadow:0 24px 70px rgba(0,0,0,.5)}
.modal-close{position:absolute;top:12px;right:16px;cursor:pointer;color:var(--sub);font-size:22px;background:none;border:none;line-height:1}
.modal-close:hover{color:var(--text)}
.tt{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed;margin-top:6px}
.tt th{background:rgba(20,20,30,.5);padding:7px 4px;color:var(--sub);font-weight:700;border:1px solid var(--border);font-size:12px}
.tt td{border:1px solid var(--border);height:46px;vertical-align:top;padding:2px}
.tt .sech,.tt .secn{width:36px;text-align:center;color:var(--sub);background:rgba(20,20,30,.45)}
.tt .secn{font-size:11px}
.clsbox{height:100%;padding:4px 6px;border-radius:6px;display:flex;flex-direction:column;gap:1px;overflow:hidden}
.clsbox b{font-size:11.5px;color:#fff;line-height:1.25}
.clsbox span{font-size:10px;color:var(--sub);line-height:1.2}
.clsbox .wk{color:var(--accent2)}
.noarr{margin-top:14px}
.noarr .lbl{color:var(--sub);font-size:12px;margin-bottom:6px}
.noarr .item{display:inline-block;background:rgba(255,255,255,.06);border:1px solid var(--border);
  border-radius:8px;padding:5px 11px;margin:0 8px 8px 0;font-size:12px}
</style></head>
<body>
<div id="bg"></div>
<div class="app">
  <div class="head"><h1>YNU 抢课助手</h1>
    <button class="ghost" style="margin-left:auto;flex:none;padding:7px 16px" onclick="openSelected()">已选课程</button>
    <button class="ghost" style="flex:none;padding:7px 16px;margin-left:8px" onclick="openTimetable()">我的课表</button>
    <div class="status" id="status" style="margin-left:16px">空闲</div></div>
  <div class="body">
    <div class="left">
      <div class="card">
        <div class="sec"><div class="bar"></div><b>账号</b></div>
        <div class="row"><label>学号</label><input id="user" placeholder="学号"></div>
        <div class="row"><label>密码</label><input id="pass" type="password" placeholder="密码"></div>
        <div class="row"><label>选课批次</label>
          <select id="batch"><option value="__BATCH__">默认批次（点“获取”更新）</option></select>
          <button class="btn" style="flex:none;padding:8px 12px" onclick="fetchBatches()">获取</button></div>
      </div>
      <div class="card">
        <div class="sec"><div class="bar"></div><b>模式（括号内为每次请求间隔）</b></div>
        <div class="mode" data-mode="turbo"><div class="rd"></div><span class="nm">turbo</span><span class="iv">（0 秒·不间断）</span><span class="wk">· 每门课 ×6</span></div>
        <div class="mode on" data-mode="fast"><div class="rd"></div><span class="nm">fast</span><span class="iv">（0.3 秒）</span><span class="wk">· 每门课 ×1</span></div>
        <div class="mode" data-mode="steady"><div class="rd"></div><span class="nm">steady</span><span class="iv">（2 秒）</span><span class="wk">· 每门课 ×1</span></div>
        <div class="mode" data-mode="custom"><div class="rd"></div><span class="nm">custom</span>
          <span class="wk">每门课</span><input class="mini" id="csalvo" value="1"><span class="wk">个·间隔</span>
          <input class="mini" id="cinterval" value="0.5"><span class="wk">秒</span></div>
        <div class="desc" id="modeDesc"></div>
        <div class="hint" id="modeHint"></div>
      </div>
      <div class="card">
        <div class="sec"><div class="bar"></div><b>高峰增强</b>
          <label class="chk" style="margin-left:auto"><input type="checkbox" id="peakEn" style="width:auto">启用</label></div>
        <div class="row"><label>每小时第</label>
          <input id="peakStart" type="number" min="0" max="59" value="43" style="width:70px"><span style="color:var(--sub)">~</span>
          <input id="peakEnd" type="number" min="0" max="59" value="45" style="width:70px"><span class="tip">分</span></div>
        <div class="row"><label>强度倍数</label>
          <input id="peakMult" type="number" min="1" step="0.5" value="4" style="width:80px"><span class="tip">倍</span></div>
        <div class="tip">每小时循环：到第 43~45 分自动强度×倍数（优先把间隔缩短为 1/倍数；若已是 turbo 间隔0 则并发×倍数）。</div>
      </div>
      <div class="card">
        <div class="sec"><div class="bar"></div><b>可选</b></div>
        <div class="row"><label>定时开抢</label><input id="startAt" type="datetime-local"></div>
        <div class="row"><label>提醒邮箱</label><input id="email" placeholder="可空"></div>
        <div class="row"><label>邮箱授权码</label><input id="eauth" type="password" placeholder="可空"></div>
      </div>
      <div class="btns">
        <button class="ghost" onclick="saveCfg()">保存配置</button>
        <button class="ghost" onclick="loadCfg()">加载配置</button>
      </div>
    </div>
    <div class="right">
      <div class="tabs">
        <div class="tab on" data-tab="query">课程查询</div>
        <div class="tab" data-tab="grab">抢课列表</div>
      </div>
      <div class="card" style="flex:1;min-height:0;display:flex;flex-direction:column;border-radius:0 16px 16px 16px">
        <div class="pane on" id="pane-query">
          <div class="qbar">
            <select id="qcat"></select>
            <input id="qkw" placeholder="搜索课名…">
            <button class="btn" onclick="doQuery()">查询</button>
            <label class="chk"><input type="checkbox" id="qonly" style="width:auto" onchange="renderResults()">仅显示有余量</label>
            <label class="chk"><input type="checkbox" id="qshowsel" checked style="width:auto" onchange="renderResults()">显示已选课程</label>
            <span class="tip" id="qstatus" style="color:var(--sub);font-size:12px"></span>
          </div>
          <div class="tablewrap">
            <table><thead><tr><th style="width:34px"></th><th>课程</th><th>教师</th><th>上课时间</th><th style="width:52px">余量</th><th style="width:66px">标记</th><th>分类</th></tr></thead>
            <tbody id="qbody"></tbody></table>
          </div>
          <div class="act"><button class="btn" onclick="addSelected()">加入抢课列表</button>
            <span class="tip">勾选后加入；满/冲突的课也能加，抢到有人退课即可</span></div>
        </div>
        <div class="pane" id="pane-grab">
          <div class="tablewrap">
            <table><thead><tr><th>备注名</th><th>教学班ID</th><th style="width:64px">类型</th><th>批次</th><th style="width:74px">状态</th><th style="width:40px"></th></tr></thead>
            <tbody id="gbody"></tbody></table>
          </div>
          <div class="addrow">
            <input id="mName" placeholder="备注名">
            <input id="mId" class="wid" placeholder="教学班ID">
            <select id="mType"><option>XGXK</option><option>TJKC</option><option>FANKC</option><option>TYKC</option><option>CXKC</option></select>
            <input id="mBatch" placeholder="批次(可空)">
            <button class="btn" onclick="addManual()">添加</button>
          </div>
          <div class="tip" style="margin-top:6px">XGXK 通识 / TJKC 推荐 / FANKC 主修 / TYKC 体育 / CXKC 创新创业</div>
        </div>
      </div>
      <div class="card log" id="logCard">
        <div class="logtop"><div class="bar" style="width:4px;height:16px;background:var(--accent);border-radius:2px"></div>
          <b>实时日志</b><span class="cnt" id="cnt">请求数 0</span>
          <button class="ghost" id="logBigBtn" style="flex:none;padding:5px 12px;margin-left:8px" onclick="toggleLogBig()">放大</button>
          <button class="ghost" style="flex:none;padding:5px 12px;margin-left:6px" onclick="document.getElementById('logbox').textContent=''">清空</button></div>
        <div class="logbox" id="logbox"></div>
      </div>
    </div>
  </div>
  <div class="foot">
    <button class="go" id="btnStart" onclick="startGrab()">开始抢课</button>
    <button class="stop" id="btnStop" onclick="stopGrab()" disabled>停止</button>
  </div>
</div>
<div class="modal" id="ttModal">
  <div class="modal-bg"></div>
  <div class="modal-card">
    <button class="modal-close" onclick="closeTimetable()">✕</button>
    <div class="sec"><div class="bar"></div><b>我的课表</b>
      <span class="tip" id="ttStatus" style="margin-left:12px"></span>
      <button class="ghost" style="margin-left:auto;flex:none;padding:6px 14px" onclick="loadTimetable()">刷新</button></div>
    <div id="ttGrid"></div>
    <div class="noarr" id="ttNoArr"></div>
  </div>
</div>
<div class="modal" id="selModal">
  <div class="modal-bg"></div>
  <div class="modal-card">
    <button class="modal-close" onclick="closeSelected()">✕</button>
    <div class="sec"><div class="bar"></div><b>已选课程</b>
      <span class="tip" id="selStatus" style="margin-left:12px"></span>
      <button class="ghost" style="margin-left:auto;flex:none;padding:6px 14px" onclick="loadSelected()">刷新</button></div>
    <div class="tablewrap" style="max-height:70vh;margin-top:8px">
      <table><thead><tr><th>课程</th><th style="width:90px">教师</th><th>时间地点</th><th style="width:56px">学分</th><th style="width:80px">分类</th><th style="width:72px">操作</th></tr></thead>
      <tbody id="selBody"></tbody></table>
    </div>
  </div>
</div>
<div class="modal" id="confModal">
  <div class="modal-bg"></div>
  <div class="modal-card" style="width:min(560px,94vw)">
    <button class="modal-close" onclick="closeConflict()">✕</button>
    <div class="sec"><div class="bar"></div><b>冲突详情</b></div>
    <div id="confBody" style="margin-top:10px;font-size:13.5px;line-height:1.7;color:var(--text);white-space:pre-wrap;word-break:break-word"></div>
    <div style="display:flex;justify-content:flex-end;margin-top:16px">
      <button class="ghost" style="flex:none;padding:7px 20px" onclick="closeConflict()">确定</button>
    </div>
  </div>
</div>
<script>
const CATS=["通识选修课 (XGXK)","推荐课程 (TJKC)","主修课程 (FANKC)","体育课程 (TYKC)","创新创业 (CXKC)"];
const MODE_DESC={
  turbo:"每一轮同时给每门课发 6 个请求，轮与轮之间不停。开抢瞬间用，火力最猛，易被限流。",
  fast:"每一轮同时给每门课发 1 个请求，间隔 0.3 秒。日常均衡之选。",
  steady:"每一轮同时给每门课发 1 个请求，间隔 2 秒。挂机稳，不易被限流。",
  custom:"自定义：用上方两个输入框设置每门课每轮并发数与轮间隔（间隔可填 0）。"};
let allResults=[], mode="fast";
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);

// 分类下拉
CATS.forEach((c,i)=>{let o=document.createElement("option");o.value=i;o.textContent=c;$("#qcat").appendChild(o);});

// 标签页
$$(".tab").forEach(t=>t.onclick=()=>{
  $$(".tab").forEach(x=>x.classList.remove("on"));t.classList.add("on");
  $$(".pane").forEach(p=>p.classList.remove("on"));
  $("#pane-"+t.dataset.tab).classList.add("on");});

// 模式
$$(".mode").forEach(m=>m.onclick=e=>{
  if(e.target.tagName==="INPUT")return;
  mode=m.dataset.mode; $$(".mode").forEach(x=>x.classList.toggle("on",x===m));
  $("#modeDesc").textContent=MODE_DESC[mode]; validateCustom();});
$("#modeDesc").textContent=MODE_DESC[mode];
$("#csalvo").oninput=validateCustom; $("#cinterval").oninput=validateCustom;
function validateCustom(){
  let s=$("#csalvo"), i=$("#cinterval"), msgs=[], okS=true, okI=true;
  let sv=parseFloat(s.value); if(!(Number.isFinite(sv)&&sv>=1)){okS=false;msgs.push("并发数需为≥1的整数");}
  let iv=parseFloat(i.value); if(!(Number.isFinite(iv)&&iv>=0)){okI=false;msgs.push("间隔需为≥0的数字");}
  s.classList.toggle("bad",!okS); i.classList.toggle("bad",!okI);
  $("#modeHint").textContent = (mode==="custom"&&msgs.length)?("注意："+msgs.join("；")):"";
  return okS&&okI;
}

function gatherCfg(){
  let courses=[...$("#gbody").querySelectorAll("tr")].map(tr=>({
    name:tr.dataset.name,id:tr.dataset.id,type:tr.dataset.type,batch:tr.dataset.batch}));
  let sa=$("#startAt").value; // yyyy-MM-ddTHH:mm
  sa = sa ? sa.replace("T"," ")+":00" : "";
  let peak={enabled:$("#peakEn").checked,startMin:$("#peakStart").value,endMin:$("#peakEnd").value,mult:$("#peakMult").value};
  return {username:$("#user").value.trim(),password:$("#pass").value,batch:$("#batch").value.trim(),
    campus:"02",mode:mode,custom_salvo:$("#csalvo").value,custom_interval:$("#cinterval").value,
    start_at:sa,email_user:$("#email").value.trim(),email_auth:$("#eauth").value.trim(),
    peak:peak,courses:courses};
}

// 统一的 API 调用：走本地 HTTP（fetch），取代不稳的 pywebview 桥接。页面加载即可用，不再抽奖。
const API_TOKEN="__TOKEN__";
async function callApi(name,...args){
  try{
    let r=await fetch("/api/"+name+"?t="+API_TOKEN,{
      method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify(args)});
    if(!r.ok){ appLog("调用出错("+name+")：HTTP "+r.status); return null; }
    return await r.json();
  }catch(e){ appLog("调用出错("+name+")："+e); return null; }
}
// 后端主动推送（日志/事件/回调）通过 SSE 收取；断线由 EventSource 自动重连
function initEvents(){
  try{
    let es=new EventSource("/events?t="+API_TOKEN);
    es.onmessage=function(ev){
      let m; try{ m=JSON.parse(ev.data); }catch(e){ return; }
      if(m.t==="log"){ appLog(m.text); }
      else if(m.t==="event"){ appEvent(m.kind,m.payload); }
      else if(m.t==="push"){ let fn=window[m.fn]; if(typeof fn==="function") fn(m.payload); }
    };
  }catch(e){ appLog("事件通道初始化失败："+e); }
}

// 选课批次
let _prevBatch="";
async function fetchBatches(){
  let cfg=gatherCfg();
  if(!cfg.username||!cfg.password){alert("请先填写学号和密码（获取批次需要登录）");return;}
  _prevBatch=$("#batch").value;
  await callApi("get_batches",cfg);   // 结果通过 window.onBatches 回调
}
window.onBatches=function(r){
  if(!r||r.error){alert("获取批次失败："+((r&&r.error)||"未知错误"));return;}
  let sel=$("#batch"); sel.innerHTML=""; let openCode=null;
  (r.batches||[]).forEach(b=>{
    let o=document.createElement("option"); o.value=b.code;
    let t=(b.beginTime||"").slice(5,16)+" ~ "+(b.endTime||"").slice(5,16);
    o.textContent=(b.open?"● ":"○ ")+b.name+"  ["+t+"]";
    sel.appendChild(o); if(b.open&&!openCode)openCode=b.code;
  });
  if(!sel.options.length){let o=document.createElement("option");o.value="";o.textContent="无可用批次";sel.appendChild(o);}
  let has=c=>[...sel.options].some(o=>o.value===c);
  sel.value = openCode || (has(_prevBatch)?_prevBatch:"") || (sel.options[0]&&sel.options[0].value) || "";
};

// 我的课表
function openTimetable(){ $("#ttModal").classList.add("on"); loadTimetable(); }
function closeTimetable(){ $("#ttModal").classList.remove("on"); }
async function loadTimetable(){
  let cfg=gatherCfg();
  if(!cfg.username||!cfg.password){$("#ttStatus").textContent="请先填学号密码";return;}
  if(!cfg.batch){$("#ttStatus").textContent="请先选择批次";return;}
  $("#ttStatus").textContent="加载中…";
  await callApi("get_timetable",cfg);   // 结果通过 window.onTimetable
}
const TT_DAYS=["周一","周二","周三","周四","周五","周六","周日"];
const TT_PALETTE=["#7c6cf5","#34d399","#fb7185","#fbbf24","#38bdf8","#f472b6","#a78bfa","#4ade80","#22d3ee","#fb923c"];
window.onTimetable=function(r){
  if(!r){return;}
  if(r.error){$("#ttStatus").textContent="失败："+r.error;$("#ttGrid").innerHTML="";return;}
  let classes=r.classes||[], noarr=r.noArranged||[];
  $("#ttStatus").textContent=`${classes.length} 节有安排，${noarr.length} 门未排时间`;
  // 颜色映射
  let cmap={},ci=0; classes.forEach(c=>{if(!cmap[c.name]){cmap[c.name]=TT_PALETTE[ci%TT_PALETTE.length];ci++;}});
  // 起始格 + 被跨行覆盖的格
  let startCell={},covered=new Set();
  classes.forEach(c=>{ if(c.day<1||c.day>7||c.begin<1)return;
    startCell[c.day+"-"+c.begin]=c;
    for(let s=c.begin+1;s<=c.end;s++)covered.add(c.day+"-"+s); });
  let SEC=12, h='<table class="tt"><thead><tr><th class="sech">节</th>'+TT_DAYS.map(d=>`<th>${d}</th>`).join("")+'</tr></thead><tbody>';
  for(let s=1;s<=SEC;s++){
    h+=`<tr><td class="secn">${s}</td>`;
    for(let d=1;d<=7;d++){
      let key=d+"-"+s;
      if(covered.has(key))continue;
      let c=startCell[key];
      if(c){ let span=Math.max(1,c.end-c.begin+1), col=cmap[c.name];
        h+=`<td rowspan="${span}"><div class="clsbox" style="background:${col}26;border-left:3px solid ${col}">
          <b>${esc(c.name)}</b><span>${esc(c.place||"")}</span><span>${esc(c.teacher||"")}</span><span class="wk">${esc(c.weeks||"")}</span></div></td>`;
      } else { h+="<td></td>"; }
    }
    h+="</tr>";
  }
  h+="</tbody></table>";
  $("#ttGrid").innerHTML=h;
  $("#ttNoArr").innerHTML = noarr.length
    ? '<div class="lbl">未安排时间的课程</div>'+noarr.map(x=>`<span class="item">${esc(x.name)}${x.teacher?(" · "+esc(x.teacher)):""}${x.credit?(" · "+esc(x.credit)+"学分"):""}</span>`).join("")
    : "";
};

// 查询
async function doQuery(){
  let cfg=gatherCfg();
  if(!cfg.username||!cfg.password){alert("请先填写学号和密码（查询需要登录）");return;}
  if(!cfg.batch){alert("请先选择/获取选课批次");return;}
  $("#qstatus").textContent="查询中…";
  await callApi("query",cfg, $("#qcat").value, $("#qkw").value.trim());  // 结果通过 onQueryResult
}
let selectedIds=[];
window.onQueryResult=function(r){
  if(!r){$("#qstatus").textContent="";return;}
  if(r.error){$("#qstatus").textContent="查询失败："+r.error;return;}
  allResults=r.results||[]; selectedIds=r.selectedIds||[]; renderResults();
};
function renderResults(){
  let only=$("#qonly").checked, showSel=$("#qshowsel").checked, tb=$("#qbody"); tb.innerHTML=""; let shown=0;
  let selSet=new Set(selectedIds);
  allResults.forEach((r,idx)=>{
    let full=r.isFull==="1"; if(only&&full)return;
    let mine=selSet.has(r.teachingClassID);
    if(mine&&!showSel)return;                 // 关掉“显示已选”时隐藏已选课程
    let conf=r.isConflict==="1";
    let flags=[]; if(mine)flags.push('<span class="tag sel">已选</span>');
    let fs=[]; if(full)fs.push("满"); if(conf)fs.push("冲突");
    let flag=fs.length?fs.join("/"):"可选";
    let hasDesc=conf&&r.conflictDesc;
    let tag = hasDesc
      ? `<span class="tag clk" data-ci="${idx}" title="${esc(r.conflictDesc)}">${flag} ⓘ</span>`
      : `<span class="tag">${flag}</span>`;
    let tr=document.createElement("tr");
    if(mine)tr.style.background="rgba(52,211,153,.08)";
    else if(conf)tr.style.background="rgba(248,113,113,.10)";   // 冲突：淡红整行（已选优先显绿）
    tr.innerHTML=`<td><input type="checkbox" data-i="${idx}" style="width:auto"></td>
      <td class="${full?'full':'ok'}">${esc(r.courseName)}</td><td>${esc(r.teacherName)}</td>
      <td>${esc(r.place)}</td><td>${r.remain==null?'-':r.remain}</td>
      <td>${flags.join(" ")}${tag}</td><td>${esc(r.cat)}</td>`;
    tb.appendChild(tr); shown++;
  });
  let selCount=allResults.filter(r=>selSet.has(r.teachingClassID)).length;
  $("#qstatus").textContent=`共 ${allResults.length} 个教学班，显示 ${shown}${selCount?("，已选 "+selCount):""}`;
}

// 已选课程 弹窗
function openSelected(){ $("#selModal").classList.add("on"); loadSelected(); }
function closeSelected(){ $("#selModal").classList.remove("on"); }
async function loadSelected(){
  let cfg=gatherCfg();
  if(!cfg.username||!cfg.password){$("#selStatus").textContent="请先填学号密码";return;}
  if(!cfg.batch){$("#selStatus").textContent="请先选择批次";return;}
  $("#selStatus").textContent="加载中…";
  await callApi("get_selected",cfg);   // 结果通过 window.onSelected
}
window.onSelected=function(r){
  if(!r)return;
  if(r.error){$("#selStatus").textContent="失败："+r.error;$("#selBody").innerHTML="";return;}
  let list=r.selected||[];
  selectedIds=list.map(x=>x.teachingClassID);   // 同步给查询列表的标记
  if(allResults.length)renderResults();
  let credit=list.reduce((s,x)=>s+(parseFloat(x.credit)||0),0);
  $("#selStatus").textContent=`共 ${list.length} 门，${credit} 学分`;
  let tb=$("#selBody"); tb.innerHTML="";
  list.forEach((x,i)=>{
    let canDel=x.canDelete==="1";
    let conf=x.isConflict==="1"?`<span class="tag clk" title="${esc(x.conflictDesc||'')}">冲突 ⓘ</span>`:"";
    let btn=canDel?`<button class="btn" style="padding:5px 12px" data-wid="${i}">退选</button>`:`<span class="tip">不可退</span>`;
    let tr=document.createElement("tr");
    tr.innerHTML=`<td>${esc(x.courseName)} ${conf}</td><td>${esc(x.teacherName)}</td>
      <td>${esc(x.place||"—")}</td><td>${esc(x.credit)}</td><td>${esc(x.typeName)}</td><td>${btn}</td>`;
    let b=tr.querySelector("[data-wid]"); if(b)b.onclick=()=>withdrawCourse(x);
    tb.appendChild(tr);
  });
};
async function withdrawCourse(x){
  if(!confirm(`确定退选：${x.courseName}？`))return;
  $("#selStatus").textContent="退选中…";
  await callApi("withdraw",gatherCfg(),x.teachingClassID);  // 完成后 onSelected 自动刷新
}
// 点“冲突ⓘ”查看和哪门课冲突
document.getElementById("qbody").addEventListener("click",e=>{
  let t=e.target.closest(".tag.clk"); if(!t)return;
  let r=allResults[+t.dataset.ci]; if(!r||!r.conflictDesc)return;
  openConflict(r.conflictDesc);
});
function openConflict(desc){ $("#confBody").textContent=desc; $("#confModal").classList.add("on"); }
function closeConflict(){ $("#confModal").classList.remove("on"); }
function addSelected(){
  let picks=[...$("#qbody").querySelectorAll("input:checked")].map(c=>allResults[+c.dataset.i]);
  if(!picks.length){alert("请先勾选要抢的课");return;}
  let n=0; picks.forEach(r=>{ if(r&&r.teachingClassID&&addGrab(r.courseName,r.teachingClassID,r.teachingClassType,r.batch))n++; });
  appLog(`已加入 ${n} 门课到抢课列表`);
  if(n){$$(".tab")[1].click();}
}

// 抢课列表
function addGrab(name,id,type,batch){
  if([...$("#gbody").querySelectorAll("tr")].some(tr=>tr.dataset.id===String(id)))return false;
  let tr=document.createElement("tr");
  tr.dataset.name=name;tr.dataset.id=id;tr.dataset.type=type;tr.dataset.batch=batch||"";
  tr.innerHTML=`<td>${esc(name)}</td><td>${esc(id)}</td><td>${esc(type)}</td><td>${esc(batch||"")}</td>
    <td class="st">待开始</td><td><span class="del">×</span></td>`;
  tr.querySelector(".del").onclick=()=>tr.remove();
  $("#gbody").appendChild(tr); return true;
}
function addManual(){
  let name=$("#mName").value.trim(), id=$("#mId").value.trim(), type=$("#mType").value, batch=$("#mBatch").value.trim();
  if(!name||!id){alert("备注名和教学班ID不能为空");return;}
  addGrab(name,id,type,batch); $("#mName").value="";$("#mId").value="";$("#mBatch").value="";
}

// 运行
async function startGrab(){
  if(mode==="custom"&&!validateCustom()){alert("自定义模式的并发数/间隔不合法");return;}
  let cfg=gatherCfg();
  if(!cfg.username||!cfg.password){alert("请填写学号和密码");return;}
  if(!cfg.courses.length){alert("请至少添加一门课程（可在课程查询里加入）");return;}
  let r=await callApi("start",cfg);
  if(!r){return;}
  if(!r.ok){alert(r.msg||"无法开始");return;}
  $("#btnStart").disabled=true; $("#btnStop").disabled=false;
  $("#status").textContent="抢课中"; $("#status").classList.add("run");
  $("#gbody").querySelectorAll("tr .st").forEach(td=>td.textContent="抢课中…");
}
async function stopGrab(){ await callApi("stop"); $("#btnStop").disabled=true; }

// 配置
async function saveCfg(){ await callApi("save_config",gatherCfg()); }
async function loadCfg(){
  let r=await callApi("load_config"); if(!r||!r.ok||!r.cfg)return; let c=r.cfg;
  $("#user").value=c.username||"";$("#pass").value=c.password||"";
  if(c.batch){let sel=$("#batch"); if(![...sel.options].some(o=>o.value===c.batch)){
      let o=document.createElement("option");o.value=c.batch;o.textContent="已存批次："+c.batch;sel.appendChild(o);} sel.value=c.batch;}
  $("#email").value=c.email_user||"";$("#eauth").value=c.email_auth||"";
  $("#csalvo").value=c.custom_salvo??"1";$("#cinterval").value=c.custom_interval??"0.5";
  mode=c.mode||"fast"; $$(".mode").forEach(x=>x.classList.toggle("on",x.dataset.mode===mode));
  $("#modeDesc").textContent=MODE_DESC[mode]||"";
  if(c.start_at){$("#startAt").value=c.start_at.slice(0,16).replace(" ","T");}else{$("#startAt").value="";}
  let pk=c.peak||{}; $("#peakEn").checked=!!pk.enabled; $("#peakStart").value=pk.startMin??"43";
  $("#peakEnd").value=pk.endMin??"45"; $("#peakMult").value=pk.mult??"4";
  $("#gbody").innerHTML=""; (c.courses||[]).forEach(x=>addGrab(x.name,x.id,x.type,x.batch));
  validateCustom();
}

// 日志放大/缩小
function toggleLogBig(){
  let c=$("#logCard"); c.classList.toggle("big");
  $("#logBigBtn").textContent=c.classList.contains("big")?"缩小":"放大";
  let b=$("#logbox"); b.scrollTop=b.scrollHeight;
}
document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){
    if($("#confModal").classList.contains("on"))closeConflict();
    else if($("#selModal").classList.contains("on"))closeSelected();
    else if($("#ttModal").classList.contains("on"))closeTimetable();
    else if($("#logCard").classList.contains("big"))toggleLogBig();
  }
});
// 点弹窗空白处（背景蒙层）关闭
document.getElementById("ttModal").addEventListener("mousedown",e=>{ if(e.target.id==="ttModal")closeTimetable(); });
document.getElementById("selModal").addEventListener("mousedown",e=>{ if(e.target.id==="selModal")closeSelected(); });
document.getElementById("confModal").addEventListener("mousedown",e=>{ if(e.target.id==="confModal")closeConflict(); });

// 被 Python 调用
let _logLines=0;
window.appLog=function(t){
  let b=$("#logbox"); b.textContent+=t+"\n"; _logLines++;
  // 长期挂机防止日志无限增长撑爆内存/拖慢渲染：超过 1200 行就只保留最近 700 行（每约 500 条才裁一次）
  if(_logLines>1200){ let ls=b.textContent.split("\n"); b.textContent=ls.slice(ls.length-700).join("\n"); _logLines=700; }
  b.scrollTop=b.scrollHeight;
};
window.appEvent=function(kind,payload){
  if(kind==="count"){$("#cnt").textContent="请求数 "+payload;}
  else if(kind==="status"){let[name,st]=payload;
    $("#gbody").querySelectorAll("tr").forEach(tr=>{if(tr.dataset.name===name)tr.querySelector(".st").textContent=st;});}
  else if(kind==="finished"){$("#btnStart").disabled=false;$("#btnStop").disabled=true;
    $("#status").textContent="空闲";$("#status").classList.remove("run");}
};
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
initEvents();   // 建立 SSE 事件通道（appLog/appEvent 已定义）
</script>
</body></html>
"""


def _dark_titlebar_later(title):
    if sys.platform != "win32":
        return
    def worker():
        try:
            from ctypes import windll, byref, sizeof, c_int
            for _ in range(20):
                hwnd = windll.user32.FindWindowW(None, title)
                if hwnd:
                    for attr in (20, 19):
                        try:
                            windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, byref(c_int(1)), sizeof(c_int))
                        except Exception:
                            pass
                    break
                time.sleep(0.2)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def main():
    global TOKEN, _API
    TOKEN = secrets.token_urlsafe(16)
    title = "YNU 抢课助手"
    api = Api()
    _API = api

    # 先在本机起服务器（界面/接口/推送都走它），窗口再加载这个本地地址
    srv, port = start_server()
    url = f"http://127.0.0.1:{port}/?t={TOKEN}"

    if webview is None:
        # 没装 pywebview 也能用：直接用系统默认浏览器打开，服务器保持运行
        print(f"未检测到 pywebview，已在浏览器打开：{url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    win = webview.create_window(title, url=url, width=1240, height=830,
                                min_size=(1060, 720), background_color="#0d0d13")
    api.window = win
    _dark_titlebar_later(title)
    webview.start()


if __name__ == "__main__":
    main()
