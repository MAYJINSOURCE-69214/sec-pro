"""Local mock verification only: these tests never contact GitHub."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import secpro


class GitHubProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proposal_id = 'a' * 32
        self.path = Path(self.temp.name) / 'outbox' / (self.proposal_id + '.json')
        self.item = {'id': 'safe-example', 'title': 'Reusable example', 'body': 'Review the example.'}
        secpro.atomic_json(self.path, {'item': self.item})
        self.settings = {'team_repo': 'owner/team', 'allow_upload': True}
        self.lib = SimpleNamespace(data=Path(self.temp.name), preview=False, settings=lambda: self.settings)
        self.branch = None
        self.remote_content = None
        self.pr = None
        self.writes = []
        self.fail_after = None
        self.get_error = None
        self.run = self.enterContext(patch('secpro.subprocess.run', side_effect=self.gh))
        self.enterContext(patch('secpro.shutil.which', return_value='mock-gh'))

    def gh(self, args, **kwargs):
        endpoint = args[2]
        method = args[4]
        payload = json.loads(kwargs['input']) if kwargs.get('input') else None
        value = None
        if method == 'GET':
            if self.get_error and '/git/ref/heads/sec-pro/' in endpoint:
                return SimpleNamespace(returncode=1, stdout='', stderr=self.get_error)
            if endpoint == 'user':
                value = {'login': 'owner'}
            elif endpoint == 'repos/owner/team':
                value = {'default_branch': 'main', 'permissions': {'push': True}}
            elif endpoint.endswith('/git/ref/heads/main'):
                value = {'object': {'sha': 'base-sha'}}
            elif '/git/ref/heads/sec-pro/' in endpoint:
                value = {'object': {'sha': self.branch}} if self.branch else None
            elif '/contents/' in endpoint:
                value = {'encoding': 'base64', 'content': base64.b64encode(self.remote_content).decode()} if self.remote_content is not None else None
            elif '/pulls?' in endpoint:
                value = [self.pr] if self.pr else []
            else:
                raise AssertionError(endpoint)
        else:
            self.writes.append((method, endpoint, payload))
            if endpoint.endswith('/git/refs'):
                self.assertIsNone(self.branch, 'must not recreate an existing branch')
                self.branch = payload['sha']
                value = {'object': {'sha': self.branch}}
            elif '/contents/' in endpoint:
                self.assertIsNone(self.remote_content, 'must not overwrite an existing file')
                self.remote_content = base64.b64decode(payload['content'])
                self.branch = 'upload-sha'
                value = {'content': {'sha': 'blob-sha'}}
            elif endpoint.endswith('/pulls'):
                self.assertIsNone(self.pr, 'must not recreate an existing PR')
                self.pr = {'html_url': 'https://github.com/owner/team/pull/1'}
                value = self.pr
            else:
                raise AssertionError(endpoint)
            if self.fail_after and self.fail_after in endpoint:
                self.fail_after = None
                return SimpleNamespace(returncode=1, stdout='', stderr='connection interrupted')
        if value is None:
            return SimpleNamespace(returncode=1, stdout='', stderr='gh: Not Found (HTTP 404)')
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')

    def submit(self):
        return secpro.github_propose(self.lib, self.proposal_id, confirm_public=True)

    def test_normal_and_completed_retry(self):
        self.assertEqual(self.submit()['url'], 'https://github.com/owner/team/pull/1')
        self.assertEqual(len(self.writes), 3)
        calls = self.run.call_count
        self.submit()
        self.assertEqual(self.run.call_count, calls)

    def test_unknown_branch_success_recovers_without_duplicate(self):
        self.fail_after = '/git/refs'
        with self.assertRaises(ValueError):
            self.submit()
        self.assertFalse(secpro.load_json(self.path).get('branch_created'))
        self.submit()
        self.assertEqual(len(self.writes), 3)

    def test_unknown_upload_success_recovers_without_duplicate(self):
        self.fail_after = '/contents/'
        with self.assertRaises(ValueError):
            self.submit()
        self.assertFalse(secpro.load_json(self.path).get('file_uploaded'))
        self.submit()
        self.assertEqual(len(self.writes), 3)

    def test_unknown_pr_success_recovers_without_duplicate(self):
        self.fail_after = '/pulls'
        with self.assertRaises(ValueError):
            self.submit()
        self.submit()
        self.assertEqual(len(self.writes), 3)

    def test_branch_success_with_checkpoint_failure_recovers(self):
        self.assert_checkpoint_failure_recovers(2)

    def test_upload_success_with_checkpoint_failure_recovers(self):
        self.assert_checkpoint_failure_recovers(3)

    def assert_checkpoint_failure_recovers(self, failure_call):
        atomic = secpro.atomic_json
        calls = 0

        def fail_checkpoint(path, value):
            nonlocal calls
            calls += 1
            if calls == failure_call:
                raise OSError('simulated local checkpoint failure')
            return atomic(path, value)

        with patch('secpro.atomic_json', side_effect=fail_checkpoint):
            with self.assertRaises(OSError):
                self.submit()
        self.submit()
        self.assertEqual(len(self.writes), 3)

    def test_existing_unowned_branch_stops_without_writes(self):
        self.branch = 'some-other-sha'
        with self.assertRaisesRegex(ValueError, '人工核对'):
            self.submit()
        self.assertEqual(self.writes, [])

    def test_foreign_content_is_not_overwritten(self):
        self.branch = 'base-sha'
        self.remote_content = b'other contributor data'
        secpro.atomic_json(self.path, {'item': self.item, 'branch_base_sha': 'base-sha'})
        with self.assertRaisesRegex(ValueError, '不会覆盖'):
            self.submit()
        self.assertEqual(self.writes, [])

    def test_non_404_query_failure_does_not_create_branch(self):
        self.get_error = 'HTTP 403 permission denied'
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(self.writes, [])

    def test_disable_guards_start_no_process(self):
        for preview, allow, confirm in [(True, True, True), (False, False, True), (False, True, False)]:
            with self.subTest(preview=preview, allow=allow, confirm=confirm):
                self.lib.preview = preview
                self.settings['allow_upload'] = allow
                with self.assertRaises(ValueError):
                    secpro.github_propose(self.lib, self.proposal_id, confirm_public=confirm)
        self.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
