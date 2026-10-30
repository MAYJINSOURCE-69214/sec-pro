import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('secpro', ROOT / 'secpro.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='secpro-test-')
        self.path = Path(self.temp.name)
        self.lib = app.Library(self.path, preview=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_is_idempotent_and_context_excludes_private_candidates(self):
        count = len(self.lib.items())
        own = self.lib.remember({'title': '私人偏好', 'body': '我习惯先看代码。'})['item']
        again = app.Library(self.path, preview=True)
        self.assertEqual(len(again.items()), count + 1)
        self.assertNotIn(own['id'], [i['id'] for i in again.context('私人偏好')['candidates']])

    def test_preview_sync_repeats_without_duplicates_or_network(self):
        with patch.object(app, 'github_catalog', side_effect=AssertionError('network forbidden')):
            first = self.lib.sync('team')
            second = self.lib.sync('team')
        self.assertEqual(first['added'], 1)
        self.assertEqual(second['unchanged'], 1)

    def test_atomic_catalog_conflict_does_not_leave_partial_entries(self):
        prior = self.lib.items()[0]
        new = {**prior, 'id': 'test-new-entry'}
        conflict = {**prior, 'body': '相同版本偷偷改内容'}
        with self.assertRaises(ValueError):
            self.lib.import_catalog({'schema': 1, 'items': [new, conflict]}, 'official')
        with self.assertRaises(ValueError):
            self.lib.get(new['id'])

    def test_team_catalog_cannot_overwrite_bundled_or_private(self):
        for item in [self.lib.items()[0], self.lib.remember({'title': '私有经验', 'body': '只在本机。'})['item']]:
            with self.assertRaises(ValueError):
                self.lib.import_catalog({'schema': 1, 'items': [{**item, 'version': '9.0.0'}]}, 'team')

    def test_updates_keep_history_and_never_downgrade(self):
        prior = self.lib.items()[0]
        result = self.lib.import_catalog({'schema': 1, 'items': [{**prior, 'version': '1.1.0', 'body': prior['body'] + '\n补充'}]}, 'official')
        self.assertEqual(result['updated'], 1)
        self.lib.import_catalog({'schema': 1, 'items': [prior]}, 'official')
        self.assertEqual(self.lib.get(prior['id'])['version'], '1.1.0')
        with self.lib.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM history WHERE id=?', (prior['id'],)).fetchone()[0], 1)

    def test_detect_sensitive_data_before_share(self):
        own = self.lib.remember({'title': '排错记录', 'body': '资料在 C:\\Users\\Example\\private，联系 me@example.org。'})['item']
        self.assertFalse(self.lib.share_preview(own['id'])['can_prepare'])
        with self.assertRaises(ValueError):
            self.lib.prepare_share(own['id'], True)

    def test_hidden_summary_is_checked_before_sharing(self):
        own = self.lib.remember({'title': '方法', 'body': '可公开的正文', 'summary': '联系 private@example.org'})['item']
        self.assertFalse(self.lib.share_preview(own['id'])['can_prepare'])
        with self.assertRaises(ValueError):
            self.lib.prepare_share(own['id'], True)

    def test_chinese_sentence_retrieves_testing_experience(self):
        selected = self.lib.context('先造假数据来测试上传功能')['candidates']
        self.assertTrue(any('测试' in item['title'] for item in selected))

    def test_share_prepare_is_local_and_requires_confirmation(self):
        own = self.lib.remember({'title': '排错方法', 'body': '保留最小复现输入与错误，修复后重跑相关检查。'})['item']
        with self.assertRaises(ValueError):
            self.lib.prepare_share(own['id'])
        with patch.object(app.subprocess, 'run', side_effect=AssertionError('external process forbidden')):
            result = self.lib.prepare_share(own['id'], True)
        proposal = json.loads((self.path / 'outbox' / (result['proposal_id'] + '.json')).read_text())
        self.assertEqual(proposal['status'], 'prepared_local')
        self.assertNotIn('personal-', json.dumps(proposal))

    def test_batch_prepares_one_proposal_after_preview_and_confirmation(self):
        ids = [self.lib.remember({'title': title, 'body': '可复用的验证方法。'})['item']['id'] for title in ('甲', '乙', '丙')]
        preview = self.lib.share_preview_batch(ids)
        self.assertTrue(preview['can_prepare'])
        with self.assertRaises(ValueError):
            self.lib.prepare_share_batch(ids, False, preview['revisions'])
        with patch.object(app.subprocess, 'run', side_effect=AssertionError('network forbidden')):
            result = self.lib.prepare_share_batch(ids, True, preview['revisions'])
        proposal = json.loads((self.path / 'outbox' / (result['proposal_id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(result['count'], 3)
        self.assertEqual(len(proposal['items']), 3)
        self.assertEqual(len({item['id'] for item in proposal['items']}), 3)
        self.assertEqual(proposal['status'], 'prepared_local')
        self.assertNotIn('personal-', json.dumps(proposal))

    def test_batch_fails_closed_on_sensitive_duplicate_and_changed_content(self):
        good = self.lib.remember({'title':'可分享', 'body':'安全方法。'})['item']['id']
        sensitive = self.lib.remember({'title':'待检查', 'body':'联系 private@example.org'})['item']['id']
        preview = self.lib.share_preview_batch([good, sensitive])
        self.assertFalse(preview['can_prepare'])
        with self.assertRaises(ValueError): self.lib.prepare_share_batch([good, sensitive], True, preview['revisions'])
        with self.assertRaises(ValueError): self.lib.share_preview_batch([good, good])
        preview = self.lib.share_preview_batch([good])
        with self.assertRaises(ValueError): self.lib.prepare_share_batch([good], True, {good:'stale'})
        self.assertFalse((self.path / 'outbox').exists())

    def test_batch_submit_creates_one_contribution_file_and_one_pr(self):
        import base64
        from types import SimpleNamespace
        ids = [self.lib.remember({'title': title, 'body': '可分享的方法。'})['item']['id'] for title in ('甲', '乙', '丙')]
        preview = self.lib.share_preview_batch(ids)
        proposal = self.lib.prepare_share_batch(ids, True, preview['revisions'])['proposal_id']
        app.atomic_json(self.path / 'settings.json', {'team_repo':'owner/repo','allow_upload':True})
        self.lib.preview = False
        requests = []
        def fake_run(args, input=None, **kwargs):
            endpoint, method = args[2], args[4]
            payload = json.loads(input) if input else None
            requests.append((endpoint, method, payload))
            if endpoint == 'user': value = {'login':'author'}
            elif endpoint == 'repos/owner/repo': value = {'default_branch':'main','permissions':{'push':True}}
            elif '/git/ref/heads/sec-pro/' in endpoint or '/contents/' in endpoint and method == 'GET':
                return SimpleNamespace(returncode=1, stderr='HTTP 404', stdout='')
            elif endpoint.endswith('/git/ref/heads/main'): value = {'object':{'sha':'a'*40}}
            elif endpoint.startswith('repos/owner/repo/pulls?'): value = []
            elif endpoint == 'repos/owner/repo/pulls': value = {'html_url':'https://github.com/owner/repo/pull/1'}
            else: value = {}
            return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps(value))
        with patch.object(app.shutil, 'which', return_value='gh'), patch.object(app.subprocess, 'run', side_effect=fake_run):
            result = app.github_propose(self.lib, proposal, True)
            self.assertEqual(app.github_propose(self.lib, proposal, True)['url'], result['url'])
        files = [p for e,m,p in requests if '/contents/' in e and m == 'PUT']
        self.assertEqual(len(files), 1)
        uploaded = json.loads(base64.b64decode(files[0]['content']))
        self.assertEqual(len(uploaded['items']), 3)
        self.assertEqual(sum(e == 'repos/owner/repo/pulls' and m == 'POST' for e,m,p in requests), 1)

    def test_identical_batch_different_order_finds_existing_pr(self):
        ids = [self.lib.remember({'title': name, 'body':'可分享的方法。'})['item']['id'] for name in ('甲','乙','丙')]
        first = self.lib.share_preview_batch(ids)
        a = self.lib.prepare_share_batch(ids, True, first['revisions'])['proposal_id']
        reverse = list(reversed(ids))
        second = self.lib.share_preview_batch(reverse)
        b = self.lib.prepare_share_batch(reverse, True, second['revisions'])['proposal_id']
        app.atomic_json(self.path / 'settings.json', {'team_repo':'owner/repo','allow_upload':False})
        path = self.path / 'outbox' / (a + '.json')
        saved = json.loads(path.read_text(encoding='utf-8'))
        saved.update(status='submitted', pr_url='https://github.com/owner/repo/pull/1')
        app.atomic_json(path, saved)
        self.assertEqual(self.lib.matching_submitted_batch(b)['url'], 'https://github.com/owner/repo/pull/1')
        app.atomic_json(self.path / 'settings.json', {'team_repo':'different/repo','allow_upload':False})
        self.assertIsNone(self.lib.matching_submitted_batch(b))

    def test_web_one_time_confirmation_uses_git_credentials_without_gh(self):
        import base64
        from types import SimpleNamespace
        from urllib.error import HTTPError
        ids = [self.lib.remember({'title':n,'body':'可公开的验证方法'})['item']['id'] for n in ('甲','乙')]
        preview = self.lib.share_preview_batch(ids)
        ident = self.lib.prepare_share_batch(ids, True, preview['revisions'])['proposal_id']
        app.atomic_json(self.path / 'settings.json', {'team_repo':'owner/repo','allow_upload':False})
        self.lib.preview = False
        calls = []
        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return 'https://api.github.com/test'
            def read(self, size): return json.dumps(self.value).encode()
        class Opener:
            def open(self, req, timeout):
                endpoint = req.full_url.split('api.github.com/', 1)[1]
                method = req.get_method()
                payload = json.loads(req.data) if req.data else None
                calls.append((endpoint, method, payload))
                if endpoint == 'user': return Response({'login':'author'})
                if endpoint == 'repos/owner/repo': return Response({'default_branch':'main','permissions':{'push':True}})
                if '/git/ref/heads/sec-pro/' in endpoint or '/contents/' in endpoint and method == 'GET':
                    raise HTTPError(req.full_url,404,'not found',{},None)
                if endpoint.endswith('/git/ref/heads/main'): return Response({'object':{'sha':'a'*40}})
                if endpoint.startswith('repos/owner/repo/pulls?'): return Response([])
                if endpoint == 'repos/owner/repo/pulls': return Response({'html_url':'https://github.com/owner/repo/pull/2'})
                return Response({})
        with patch.object(app, 'find_github_cli', return_value=None), \
             patch.object(app.shutil, 'which', return_value='git'), \
             patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stdout='password=mock-token\n',stderr='')), \
             patch('urllib.request.build_opener', return_value=Opener()):
            with self.assertRaises(ValueError): app.github_propose(self.lib, ident, True)
            result = app.github_propose(self.lib, ident, True, confirmed_ui=True)
        self.assertEqual(result['url'], 'https://github.com/owner/repo/pull/2')
        payload = next(payload for endpoint,method,payload in calls if '/contents/' in endpoint and method == 'PUT')
        self.assertEqual(len(json.loads(base64.b64decode(payload['content']))['items']), 2)
        self.assertFalse(self.lib.settings()['allow_upload'], 'one-time confirmation must not enable persistent uploads')

    def test_skill_activation_stays_inside_preview(self):
        skill = next(i for i in self.lib.items() if i['kind'] == 'skill')
        with self.assertRaises(ValueError):
            self.lib.activate_skill(skill['id'])
        self.lib.activate_skill(skill['id'], True)
        self.assertTrue(list((self.path / 'preview-codex/skills').glob('*/SKILL.md')))

    def test_worker_model_must_be_explicit(self):
        result = app.worker_request(self.lib, 'reader', '读取给定文件并指出证据。')
        self.assertEqual(result['model'], 'gpt-6-luna')
        self.assertEqual(result['fork_turns'], 'none')
        app.atomic_json(self.path / 'models.json', {'reader': {'model': 'inherit', 'effort': 'high'}})
        with self.assertRaises(ValueError):
            app.worker_request(self.lib, 'reader', '读取文件。')

    def test_upload_disabled_without_any_external_call(self):
        with patch.object(app.subprocess, 'run', side_effect=AssertionError('external process forbidden')):
            with self.assertRaises(ValueError):
                app.github_propose(self.lib, 'a' * 32, True)

    def test_remote_repository_validation_precedes_network(self):
        with patch.object(app, 'urlopen', side_effect=AssertionError('network forbidden')):
            with self.assertRaises(ValueError):
                app.github_catalog('../../other', 'main', 'library/catalog.json')


if __name__ == '__main__':
    unittest.main()
