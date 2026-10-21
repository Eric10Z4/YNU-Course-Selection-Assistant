"""Durable task journal. An interrupted submission is never silently replayed."""
import copy
import json
import os
from pathlib import Path
import threading
import time

SECRET_KEYS = {'password', 'email_auth', 'token', 'cookies', 'email_user'}
ACTIVE = {'running', 'waiting_network', 'waiting_start', 'reconciling', 'submitting'}


def public_config(value):
    if isinstance(value, dict):
        return {key: public_config(item) for key, item in value.items() if key not in SECRET_KEYS}
    if isinstance(value, list):
        return [public_config(item) for item in value]
    return value


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = {'schema': 1, 'state': 'idle', 'courses': [], 'pending': None,
                     'last_sync': None, 'message': '尚未启动任务', 'config': {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if self.data.get('schema') != 1:
                raise ValueError('任务记录版本不支持，请先导出并处理旧记录')
            if self.data['state'] in ACTIVE:
                self.data['state'] = 'interrupted'
                self.data['message'] = '上次任务已中断；请核对后手动恢复'
                self.save()

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(public_config(self.data), stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != 'nt':
                descriptor = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

    def set(self, state, message, **values):
        with self.lock:
            self.data.update(values, state=state, message=message)
            self.save()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def begin(self, cfg, resume=False):
        with self.lock:
            if not resume:
                if self.data.get('pending'):
                    raise ValueError('有结果待核对的提交，请先核对恢复，不能新建覆盖')
                self.data['courses'] = [dict(course, state='queued') for course in cfg['courses']]
            else:
                previous = self.data['config']
                old = [(c['id'], c.get('batch') or previous.get('batch')) for c in self.data['courses']]
                new = [(c['id'], c.get('batch') or cfg.get('batch')) for c in cfg['courses']]
                if old != new or previous.get('username') != cfg.get('username'):
                    raise ValueError('恢复时账号、批次和课程必须与中断任务一致')
            self.data['config'] = public_config(cfg)
            self.set('reconciling', '开始前核对已选课程')

    def pending(self, course, operation='select'):
        with self.lock:
            if self.data.get('pending'):
                raise ValueError('前一提交尚未核对')
            self.set('submitting', '正在提交，请勿重复操作', pending={
                'id': course['id'], 'batch': course.get('batch') or self.data['config'].get('batch'),
                'operation': operation, 'at': time.time()})

    def acknowledged(self, course_id, success):
        with self.lock:
            for course in self.data['courses']:
                if course['id'] == course_id:
                    course['state'] = 'succeeded' if success else 'queued'
            state = self.data['state']
            stopped = state in {'stopped', 'interrupted', 'expired'}
            self.set(state if stopped else 'running',
                     self.data['message'] if stopped else '提交结果已确认', pending=None)

    def reconcile(self, selected_by_batch):
        with self.lock:
            pending = self.data.get('pending')
            resolved = not pending
            if pending:
                selected = selected_by_batch[str(pending['batch'])]
                found = str(pending['id']) in selected
                resolved = found if pending['operation'] == 'select' else not found
                if resolved:
                    self.data['pending'] = None
            for course in self.data['courses']:
                batch = str(course.get('batch') or self.data['config']['batch'])
                course['state'] = 'succeeded' if str(course['id']) in selected_by_batch[batch] else 'queued'
            self.data['last_sync'] = time.time()
            self.set('running' if resolved else 'needs_review',
                     '已核对已选结果' if resolved else '提交结果仍不明确；请先到学校系统确认，当前不会自动重试')
            return resolved

    def stop(self, message='已停止；不会自动恢复'):
        self.set('stopped', message)
