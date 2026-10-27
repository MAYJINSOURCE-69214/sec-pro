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
