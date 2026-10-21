"""Android adapter around the existing school's session/query implementation."""
import json
from pathlib import Path
import re
import threading
import time
from collections import deque
from urllib.parse import quote, urlsplit

from mobile_policy import Journal, public_config


class NativeOcr:
    def __init__(self, native):
        self.native = native

    def classification(self, data):
        return str(self.native.classify(data))


def load_engine(native_ocr):
    # The desktop OCR wheel is not an Android dependency. Keep its public API,
    # and delegate preprocessing/inference to Android's ONNX Runtime instead.
    import qiangke_web as desktop
    import requests
    from requests.adapters import HTTPAdapter

    class MobileSession(requests.Session):
        def __init__(self, gate):
            super().__init__()
            self.gate = gate
            self.mount('https://', HTTPAdapter(max_retries=0))
            self.headers['User-Agent'] = desktop.UA

        def request(self, method, url, **kwargs):
            self.gate.check_budget()
            target = urlsplit(url)
            if target.scheme != 'https' or target.hostname != 'xk.ynu.edu.cn':
                raise ValueError('移动端只允许学校 HTTPS 接口')
            if not self.gate.available():
                raise OSError('网络不可用，等待恢复')
            # Session cookies/token remain in this Python process. No WebView
            # cookie translation, automatic redirect or transport replay.
            kwargs['allow_redirects'] = False
            kwargs['timeout'] = (8, 20)
            return super().request(method, url, **kwargs)

    class Engine(desktop.GrabEngine):
        def build_session(self):
            return MobileSession(self.gate)

        def get_ocr(self):
            return NativeOcr(native_ocr)

    return Engine, desktop


class NetworkGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.local = threading.local()
        self.state = {'available': False, 'captive': False, 'validated': False, 'generation': 0}

    def update(self, value):
        with self.condition:
            identity = value.get('identity', '')
            previous = self.state
            generation = previous['generation']
            if any(previous.get(key) != value.get(key) for key in ('available', 'captive', 'identity')):
                generation += 1
            self.state = dict(value, generation=generation)
            self.condition.notify_all()

    def available(self):
        with self.condition:
            return self.state['available'] and not self.state.get('captive')

    def snapshot(self):
        with self.condition:
            return dict(self.state)

    def begin_operation(self):
        self.local.remaining = 20
        self.local.deadline = time.monotonic() + 45

    def check_budget(self):
        if getattr(self.local, 'remaining', 0) <= 0 or time.monotonic() > getattr(self.local, 'deadline', 0):
            raise OSError('本次请求或登录次数达到上限')
        self.local.remaining -= 1


class Runtime:
    def __init__(self, directory, native_ocr=None, engine_factory=None):
        self.journal = Journal(Path(directory) / 'task-journal.json')
        self.gate = NetworkGate()
        self.logs = deque(maxlen=250)
        self.guard = threading.RLock()
        self.io_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.cfg = {}
        self.log_id = 0
        self.auth_account = None
        self.desktop = None
        if engine_factory is None:
            engine_factory, self.desktop = load_engine(native_ocr)
        self.engine = engine_factory(self.log, lambda *_: None)
        self.engine.gate = self.gate

    def log(self, text):
        text = str(text)
        for key in ('password', 'email_auth', 'username'):
            value = str(self.cfg.get(key) or '')
            if value:
                text = text.replace(value, '[已隐藏]').replace(quote(value, safe=''), '[已隐藏]')
        text = re.sub(r'https?://[^\s]+', '[接口地址已隐藏]', text)
        with self.guard:
            self.log_id += 1
            self.logs.append({'id': self.log_id, 'at': time.time(), 'text': text[:300]})

    def network(self, value):
        self.gate.update(value)

    def snapshot(self):
        result = self.journal.snapshot()
        with self.guard:
            result.update(network=self.gate.snapshot(), logs=list(self.logs),
                          active=bool(self.worker and self.worker.is_alive() and not self.stop_event.is_set()))
        return result

    @staticmethod
    def normalize(cfg):
        cfg = dict(cfg)
        if not cfg.get('username') or not cfg.get('password') or not cfg.get('batch'):
            raise ValueError('请填写学号、密码并选择批次')
        cfg['courses'] = [dict(c) for c in cfg.get('courses', [])]
        for course in cfg['courses']:
            if not all(course.get(key) for key in ('id', 'name', 'type')):
                raise ValueError('课程缺少教学班 ID、名称或类型')
            course['id'] = str(course['id'])
        keys = [(c['id'], c.get('batch') or cfg['batch']) for c in cfg['courses']]
        if len(set(keys)) != len(keys):
            raise ValueError('请移除重复教学班')
        cfg['interval'] = max(1.0, min(60.0, float(cfg.get('interval', 2))))
        cfg['duration_minutes'] = max(1.0, min(180.0, float(cfg.get('duration_minutes', 30))))
        cfg['email_user'] = cfg['email_auth'] = ''
        return cfg

    def account(self, cfg):
        identity = (cfg.get('username'), cfg.get('password'))
        if self.auth_account != identity:
            if self.engine.session:
                self.engine.session.close()
            self.engine.session = None
            self.engine.invalidate_auth()
            self.auth_account = identity
        self.cfg = cfg

    def start(self, cfg, resume=False):
        with self.guard:
            if self.worker and self.worker.is_alive():
                raise ValueError('任务尚未结束，请等待停止完成')
            cfg = self.normalize(cfg)
            if not cfg['courses']:
                raise ValueError('请先添加课程')
            start_at = float(cfg.get('start_at_ms') or 0) / 1000
            now = time.time()
            if start_at and start_at < now - 120:
                raise ValueError('计划时间已过期，请重新设置')
            if start_at > now + cfg['duration_minutes'] * 60:
                raise ValueError('定时开始须在本次运行时长内')
            self.account(cfg)
            self.journal.begin(cfg, resume)
            self.stop_event.clear()
            self.engine.stop_flag.clear()
            self.worker = threading.Thread(target=self.run, args=(cfg,), daemon=True)
            self.worker.start()
        return {'ok': True}

    def stop(self, message='已停止；不会自动恢复'):
        with self.guard:
            self.stop_event.set()
            self.engine.stop()
            self.journal.stop(message)
        with self.gate.condition:
            self.gate.condition.notify_all()
        return {'ok': True}

    def transition(self, state, message):
        with self.guard:
            if self.stop_event.is_set():
                return False
            self.journal.set(state, message)
            return True

    def reconcile(self, cfg):
        data = self.journal.snapshot()
        batches = {str(c.get('batch') or cfg['batch']) for c in data['courses']}
        if data.get('pending'):
            batches.add(str(data['pending']['batch']))
        selected = {}
        for batch in batches:
            items, error = self.engine.query_selected(dict(cfg, batch=batch))
            if error:
                raise OSError('学校查询失败或登录失效，请稍后重试')
            selected[batch] = {str(item['teachingClassID']) for item in items}
        with self.guard:
            if self.stop_event.is_set():
                return False
            return self.journal.reconcile(selected)

    def submit(self, course, cfg):
        if self.stop_event.is_set():
            return
        if not self.engine.ensure_login(cfg['username'], cfg['password']):
            raise OSError('登录未成功，暂停并退避')
        if self.stop_event.is_set():
            return
        with self.guard:
            if self.stop_event.is_set():
                return
            self.journal.pending(course)  # Durable before the first mutating byte.
        body = {'data': {'operationType': '1', 'studentCode': cfg['username'],
                        'electiveBatchCode': course.get('batch') or cfg['batch'],
                        'teachingClassId': course['id'], 'isMajor': '1',
                        'campus': cfg.get('campus', '02'), 'teachingClassType': course['type']}}
        response = self.engine.session.post(
            'https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteer.do',
            headers=self.engine._std_headers(), cookies=self.engine._cookies(),
            data='addParam=' + quote(json.dumps(body)))
        if response.status_code != 200:
            if response.status_code in (401, 403):
                self.engine.invalidate_auth()
            raise OSError('提交响应异常，必须核对已选结果')
        result = response.json()
        if 'code' not in result:
            raise OSError('提交响应不完整，必须核对已选结果')
        code = str(result['code'])
        if code == '302':
            self.engine.invalidate_auth()
        self.journal.acknowledged(course['id'], code == '1')
        self.log(f"{course['name']}：{'已成功' if code == '1' else '本次未成功'}")

    def run(self, cfg):
        deadline = time.monotonic() + cfg['duration_minutes'] * 60
        generation = -1
        failures = 0
        cursor = 0
        try:
            while not self.stop_event.is_set():
                if time.monotonic() >= deadline:
                    self.transition('expired', '本次运行时间已到，请手动决定是否继续')
                    return
                start_at = float(cfg.get('start_at_ms') or 0) / 1000
                if start_at > time.time():
                    if not self.transition('waiting_start', '等待计划时间；通知栏可随时停止'): return
                    self.stop_event.wait(min(5, start_at - time.time()))
                    continue
                if not self.gate.available():
                    if not self.transition('waiting_network', '等待可用网络；校园网认证请先完成'): return
                    self.stop_event.wait(2)
                    continue
                current_generation = self.gate.snapshot()['generation']
                with self.io_lock:
                    try:
                        self.gate.begin_operation()
                        if current_generation != generation or self.journal.snapshot().get('pending'):
                            if not self.transition('reconciling', '网络恢复，正在核对登录和已选结果'): return
                            self.engine.invalidate_auth()
                            if not self.reconcile(cfg):
                                return
                            generation = current_generation
                        courses = [c for c in self.journal.snapshot()['courses'] if c['state'] != 'succeeded']
                        if not courses:
                            self.transition('completed', '全部目标课程已确认选上')
                            return
                        if not self.transition('running', '正在执行；提交异常时先核对'): return
                        self.submit(courses[cursor % len(courses)], cfg)
                        cursor += 1
                        failures = 0
                    except Exception as exc:
                        if self.stop_event.is_set():
                            return
                        failures += 1
                        self.log(f'请求未完成（{type(exc).__name__}），先等待再核对')
                        generation = -1
                        if failures >= 5:
                            self.transition('needs_review', '连续请求或登录失败，已暂停，请检查网络和账号')
                            return
                self.stop_event.wait(max(cfg['interval'], min(60, 2 ** failures) if failures else 0))
        finally:
            # Preserve the stopped/interrupted/uncertain state; never auto-start.
            with self.guard:
                if self.journal.snapshot()['state'] in {'running', 'submitting', 'reconciling'}:
                    self.journal.set('interrupted', '任务已中断，请核对后恢复')

    def command(self, method, cfg, extra=None):
        extra = extra or {}
        if method == 'snapshot':
            return dict(ok=True, snapshot=self.snapshot())
        if method == 'stop':
            return self.stop()
        if method in ('start', 'resume'):
            return self.start(cfg, method == 'resume')
        with self.io_lock:
            self.gate.begin_operation()
            if self.worker and self.worker.is_alive():
                raise ValueError('任务执行中，请先停止后再进行独立查询或退选')
            if not self.gate.available():
                raise ValueError('网络不可用或需要认证，请连接后重试')
            if not cfg.get('username') or not cfg.get('password'):
                raise ValueError('请填写学号和密码')
            self.account(cfg)
            if method == 'batches':
                value, error = self.engine.query_batches(cfg)
            elif method == 'types':
                value, error = self.engine.query_course_types(cfg)
            elif method == 'query':
                if not cfg.get('batch'):
                    raise ValueError('请先选择批次')
                kind = str(extra.get('type', 'XGXK'))
                endpoint = {'XGXK': 'publicCourse.do', 'TJKC': 'recommendedCourse.do'}.get(kind, 'programCourse.do')
                value, error = self.engine.query_courses(cfg, endpoint, kind, str(extra.get('keyword', '')), max_pages=5)
            elif method in ('selected', 'timetable'):
                if not cfg.get('batch'):
                    raise ValueError('请先选择批次')
                value, error = (self.engine.query_selected(cfg) if method == 'selected' else self.engine.query_timetable(cfg))
            elif method == 'recheck':
                self.check_identity(cfg)
                self.stop_event.clear()
                resolved = self.reconcile(cfg)
                if resolved:
                    self.journal.set('stopped', '核对完成，请手动恢复任务')
                return {'ok': resolved, 'msg': self.journal.snapshot()['message']}
            elif method == 'confirm_review':
                self.check_identity(cfg)
                if extra.get('confirmed') is not True:
                    raise ValueError('必须由用户在学校系统核对后明确确认')
                self.journal.set('stopped', '用户已人工核对，允许下次手动恢复', pending=None)
                return {'ok': True}
            elif method == 'withdraw':
                # Never use the desktop helper's implicit 401 replay: this GET
                # changes server state and is treated exactly like a POST.
                if self.journal.snapshot().get('pending'):
                    raise ValueError('先处理上次待核对提交')
                if not cfg.get('batch') or not extra.get('id'):
                    raise ValueError('退选需要批次与教学班 ID')
                self.engine.ensure_session()
                if not self.engine.ensure_login(cfg['username'], cfg['password']):
                    raise ValueError('登录失败')
                self.journal.set('stopped', '准备退选', config=public_config(cfg), courses=[])
                self.journal.pending({'id': str(extra['id']), 'batch': cfg['batch']}, 'withdraw')
                from urllib.parse import urlencode
                param = {'data': {'operationType': '2', 'studentCode': cfg['username'],
                                 'electiveBatchCode': cfg['batch'], 'teachingClassId': str(extra['id']), 'isMajor': '1'}}
                try:
                    response = self.engine.session.get('https://xk.ynu.edu.cn/xsxkapp/sys/xsxkapp/elective/deleteVolunteer.do?' +
                        urlencode({'timestamp': int(time.time() * 1000), 'deleteParam': json.dumps(param)}),
                        headers=self.engine._std_headers(), cookies=self.engine._cookies())
                    result = response.json()
                    if response.status_code != 200 or 'code' not in result:
                        raise OSError('响应不完整')
                    self.journal.set('stopped', '退选响应已确认', pending=None)
                    return {'ok': str(result['code']) == '1', 'msg': '退选成功' if str(result['code']) == '1' else '本次退选未成功'}
                except Exception:
                    self.journal.set('needs_review', '退选结果不明确，先查询已选，不会自动重试')
                    return {'ok': False, 'msg': self.journal.snapshot()['message']}
            else:
                raise ValueError('不支持的移动端操作')
            if not error:
                with self.journal.lock:
                    self.journal.data['last_sync'] = time.time()
                    self.journal.save()
            return {'ok': not bool(error), 'data': value if not error else None,
                    'msg': '查询失败，请检查网络或登录' if error else ''}

    def check_identity(self, cfg):
        previous = self.journal.snapshot()['config']
        if previous.get('username') != cfg.get('username') or previous.get('batch') != cfg.get('batch'):
            raise ValueError('请使用待核对任务原来的账号和批次')


_runtime = None


def initialize(directory, native_ocr):
    global _runtime
    if _runtime is None:
        _runtime = Runtime(directory, native_ocr)
    return True


def call(method, payload='{}'):
    try:
        value = json.loads(payload)
        return json.dumps(_runtime.command(method, value.get('cfg', {}), value.get('extra', {})), ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return json.dumps({'ok': False, 'msg': str(exc)}, ensure_ascii=False)
    except Exception:
        return json.dumps({'ok': False, 'msg': '操作未完成，请查看任务状态并核对结果'}, ensure_ascii=False)


def network(value):
    _runtime.network(json.loads(value))


def stop(message):
    if _runtime:
        _runtime.stop(message)
