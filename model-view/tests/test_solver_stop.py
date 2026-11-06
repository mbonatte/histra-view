import json
import time
import unittest
import uuid
import zipfile
from unittest.mock import patch

from builder_api import build, defaults
from solver_api import RUNS_DIR, start_job, stop_job, job_status, _LambdaCrossing
from histra import AnalysisSession


class SolverStopTests(unittest.TestCase):
    def test_zero_target_waits_for_departure_and_first_return(self):
        crossing = _LambdaCrossing(0.0)
        self.assertFalse(crossing.observe(0.0))
        self.assertFalse(crossing.observe(-0.045716))
        self.assertFalse(crossing.observe(-0.006032))
        self.assertTrue(crossing.observe(0.003872))
        self.assertEqual(crossing.achieved, 0.003872)

    def test_nonzero_target_detects_crossing_from_initial_state(self):
        crossing = _LambdaCrossing(-0.1)
        self.assertFalse(crossing.observe(-0.05))
        self.assertTrue(crossing.observe(-0.12))

    def test_stop_after_committed_step_exports_incomplete_archive(self):
        payload = defaults(); payload['nl'] = 200
        source = build({'mode': 'create', 'payload': payload})
        name = f'stop_test_{uuid.uuid4().hex}'
        original = AnalysisSession.run
        def run_with_stop(session, *args, **kwargs):
            prior = kwargs['should_stop_after_commit']
            def trigger(step):
                stop_job()
                return prior(step)
            kwargs['should_stop_after_commit'] = trigger
            return original(session, *args, **kwargs)
        bundle = RUNS_DIR / f'{name}.histra'
        try:
            with patch.object(AnalysisSession, 'run', run_with_stop):
                initial = start_job(source, name + '.hrx', 'Vert')
                deadline = time.monotonic() + 120
                while True:
                    status = job_status(initial['jobId'])
                    if status['status'] != 'running': break
                    if time.monotonic() > deadline: self.fail('stop test timed out')
                    time.sleep(.05)
            self.assertEqual(status['status'], 'stopped', status.get('error'))
            self.assertEqual(status['stages'][0]['status'], 'stopped')
            self.assertEqual(status['stages'][0]['steps'], 1)
            self.assertTrue(status['bundleReady'])
            self.assertEqual(status['analysisStates']['1']['State'], 'ExecutedNotCompleted')
            with zipfile.ZipFile(bundle) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                metrics = manifest['cases']['Vert']['summary']['metrics']
                self.assertEqual(metrics['outcome'], 'stopped')
                self.assertFalse(metrics['completed'])
                self.assertEqual(metrics['committed_steps'], 1)
            from histra_results import project_histra
            projected = project_histra(bundle, 'Vert', include_stress_fields=False, include_modal_shapes=False)
            self.assertEqual(projected['analyses'][0]['outcome'], 'stopped')
            self.assertEqual(projected['analyses'][0]['steps'][-1]['step'], 1)
        finally:
            bundle.unlink(missing_ok=True)

    def test_cancel_does_not_signal_finished_before_results_export(self):
        from solver_api import cancel_job
        payload = defaults(); payload['nl'] = 200
        source = build({'mode': 'create', 'payload': payload})
        name = f'cancel_test_{uuid.uuid4().hex}'
        original = AnalysisSession.run
        completion_status = []
        def run_with_cancel(session, *args, **kwargs):
            callback = kwargs['on_step_committed']
            def trigger(step, analysis):
                callback(step, analysis)
                cancel_job()
            kwargs['on_step_committed'] = trigger
            return original(session, *args, **kwargs)
        def completed(job):
            completion_status.append(job['status'])
        bundle = RUNS_DIR / f'{name}.histra'
        try:
            with patch.object(AnalysisSession, 'run', run_with_cancel):
                initial = start_job(source, name + '.hrx', 'Vert', on_complete=completed)
                deadline = time.monotonic() + 120
                while True:
                    status = job_status(initial['jobId'])
                    if status['status'] != 'running': break
                    if time.monotonic() > deadline: self.fail('cancel test timed out')
                    time.sleep(.05)
            self.assertEqual(status['status'], 'cancelled')
            self.assertTrue(status['bundleReady'])
            self.assertEqual(completion_status, ['running'])
        finally:
            bundle.unlink(missing_ok=True)
