"""Failure scenarios use a fake school session; no school traffic is generated."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

if not hasattr(sys, 'getandroidapilevel'):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'android/app/src/main/python'))
from mobile_policy import Journal
from android_runtime import Runtime, NetworkGate

CFG = {'username': 'synthetic-user', 'password': 'synthetic-password', 'batch': 'batch-a',
       'courses': [{'id': 'class-a', 'name': '合成测试课程', 'type': 'XGXK'}], 'duration_minutes': 1}


class Response:
    status_code = 200
    def json(self): return {'code': '1'}


class FakeEngine:
    def __init__(self, log, event):
        self.stop_flag = threading.Event()
        self.session = self
        self.selected = set()
        self.submissions = 0
        self.queries = 0
        self.lose_response = False
    def close(self): pass
    def invalidate_auth(self): pass
    def stop(self): self.stop_flag.set()
    def ensure_login(self, *_): return True
    def ensure_session(self): self.session = self
    def _std_headers(self): return {}
    def _cookies(self): return {}
    def query_selected(self, cfg):
        self.queries += 1
        return [{'teachingClassID': item} for item in self.selected], None
    def post(self, *args, **kwargs):
        self.submissions += 1
        if self.lose_response: raise OSError('synthetic response lost')
        self.selected.add('class-a')
        return Response()


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'task.json'
        self.journal = Journal(self.path)
        self.journal.begin(CFG)

    def test_process_death_retains_pending_and_never_restarts(self):
        self.journal.pending(CFG['courses'][0])
        recovered = Journal(self.path).snapshot()
        self.assertEqual(recovered['state'], 'interrupted')
        self.assertEqual(recovered['pending']['id'], 'class-a')
        self.assertNotIn('password', recovered['config'])

    def test_lost_response_without_confirmed_result_blocks_replay(self):
        self.journal.pending(CFG['courses'][0])
        self.assertFalse(self.journal.reconcile({'batch-a': set()}))
        self.assertEqual(self.journal.snapshot()['state'], 'needs_review')
        with self.assertRaises(ValueError): self.journal.begin(CFG)
        with self.assertRaises(ValueError): self.journal.pending(CFG['courses'][0])

    def test_lost_response_confirmed_selected_is_not_resubmitted(self):
        self.journal.pending(CFG['courses'][0])
        self.assertTrue(self.journal.reconcile({'batch-a': {'class-a'}}))
        self.assertIsNone(self.journal.snapshot()['pending'])
        self.assertEqual(self.journal.snapshot()['courses'][0]['state'], 'succeeded')

    def test_withdraw_get_requires_confirmation_of_absence(self):
        self.journal.pending(CFG['courses'][0], 'withdraw')
        self.assertFalse(self.journal.reconcile({'batch-a': {'class-a'}}))
        self.assertTrue(self.journal.reconcile({'batch-a': set()}))

    def test_stopped_task_is_still_stopped_after_late_success(self):
        self.journal.pending(CFG['courses'][0]); self.journal.stop()
        self.journal.acknowledged('class-a', True)
        self.assertEqual(Journal(self.path).snapshot()['state'], 'stopped')

    def test_resume_rejects_different_account_or_course_batch(self):
        for changed in (dict(CFG, username='other'), dict(CFG, batch='other')):
            with self.assertRaises(ValueError): self.journal.begin(changed, resume=True)

    def test_reconciliation_is_per_batch(self):
        cfg = dict(CFG, courses=[dict(CFG['courses'][0], batch='batch-b')])
        self.journal.begin(cfg)
        self.journal.reconcile({'batch-b': set()})
        self.assertEqual(self.journal.snapshot()['courses'][0]['state'], 'queued')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(self.temp.name, engine_factory=FakeEngine)
        self.runtime.network({'available': True, 'captive': False, 'validated': True, 'identity': 'wifi'})
        self.runtime.cfg = CFG
        # Preserve the injected session across the synthetic account transition.
        self.runtime.auth_account = (CFG['username'], CFG['password'])

    def test_offline_task_stops_without_network_or_submissions(self):
        self.runtime.network({'available': False, 'captive': False})
        self.runtime.start(CFG)
        self.runtime.stop()
        self.runtime.worker.join(2)
        self.assertFalse(self.runtime.worker.is_alive())
        self.assertEqual(self.runtime.engine.submissions, 0)
        self.assertEqual(self.runtime.engine.queries, 0)

    def test_reconnect_checks_selected_before_submitting(self):
        self.runtime.engine.selected.add('class-a')
        self.runtime.start(CFG); self.runtime.worker.join(3)
        self.assertEqual(self.runtime.engine.submissions, 0)
        self.assertGreater(self.runtime.engine.queries, 0)
        self.assertEqual(self.runtime.snapshot()['state'], 'completed')

    def test_submission_is_durable_before_transport_failure(self):
        self.runtime.journal.begin(CFG)
        self.runtime.engine.lose_response = True
        with self.assertRaises(OSError): self.runtime.submit(CFG['courses'][0], CFG)
        self.assertEqual(Journal(self.runtime.journal.path).snapshot()['pending']['id'], 'class-a')
        self.assertEqual(self.runtime.engine.submissions, 1)

    def test_captive_network_is_not_ready(self):
        self.runtime.network({'available': True, 'captive': True})
        with self.assertRaises(ValueError): self.runtime.command('selected', CFG)

    def test_switching_network_requires_new_reconciliation_generation(self):
        before = self.runtime.gate.snapshot()['generation']
        self.runtime.network({'available': True, 'captive': False, 'identity': 'mobile'})
        self.assertGreater(self.runtime.gate.snapshot()['generation'], before)

    def test_expired_schedule_is_not_executed(self):
        with self.assertRaises(ValueError): self.runtime.start(dict(CFG, start_at_ms=(time.time()-1000)*1000))
        self.assertEqual(self.runtime.engine.submissions, 0)

    def test_pending_cannot_be_cleared_from_another_account(self):
        self.runtime.journal.begin(CFG); self.runtime.journal.pending(CFG['courses'][0])
        with self.assertRaises(ValueError): self.runtime.command('confirm_review',dict(CFG, username='other'),{'confirmed':True})
        self.assertIsNotNone(self.runtime.journal.snapshot()['pending'])

    def test_log_redacts_password_and_query_urls(self):
        self.runtime.log('synthetic-password https://example.invalid/?token=secret')
        message = self.runtime.snapshot()['logs'][0]['text']
        self.assertNotIn(CFG['password'], message); self.assertNotIn('token=secret', message)

    def test_auth_redirect_loop_has_bounded_request_budget(self):
        gate = NetworkGate(); gate.begin_operation()
        for _ in range(20): gate.check_budget()
        with self.assertRaises(OSError): gate.check_budget()


def run_device_tests():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    return json.dumps({'tests': result.testsRun, 'passed': result.wasSuccessful(), 'report': stream.getvalue()})


def install_offline_scenario():
    import android_runtime
    android_runtime._runtime.stop()
    runtime = Runtime(tempfile.mkdtemp(prefix='ynu-synthetic-'), engine_factory=FakeEngine)
    runtime.auth_account = (CFG['username'], CFG['password'])
    runtime.network({'available': False, 'captive': False, 'validated': False, 'identity': ''})
    android_runtime._runtime = runtime
    return json.dumps({'cfg': CFG})


if __name__ == '__main__': unittest.main()
