import concurrent.futures
import copy
from datetime import datetime,timezone,timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch,MagicMock
import workers

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name);self.pool=workers.Workers(self.data)

    def spec(self,key='job-a',model='gpt-coder',**extra):
        return {'role':'coder','model_key':model,'task_key':key,'task':'根据给定代码提出修复方案。','reason':'本工单先验证接口与产物，暂不主张已有性能依据。','evaluation':True,'resources':[],**extra}

    def external(self):
        c=self.pool.config();c['providers']['kimi']['enabled']=True;c['models']['company-kimi']['model']='company-model-version'
        self.pool.save(c)
        return patch.dict(os.environ,{'COMPANY_KIMI_API_KEY':'synthetic-test-token'})

    def test_native_and_external_share_limit_and_no_duplicate(self):
        with self.external():
            a=self.pool.reserve(self.spec())
            self.pool.reserve(self.spec('job-b','company-kimi'))
            with self.assertRaisesRegex(ValueError,'名额'): self.pool.reserve(self.spec('job-c'))
            with self.assertRaisesRegex(ValueError,'已存在'): self.pool.reserve(self.spec())
            self.pool.finish(a['job_id'],'completed','native worker stopped')
            self.pool.reserve(self.spec('job-c'))

    def test_atomic_reservation_across_independent_connections(self):
        def reserve(i):
            try: workers.Workers(self.data).reserve(self.spec('job-'+str(i)));return True
            except ValueError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            results=list(executor.map(reserve,range(6)))
        self.assertEqual(sum(results),2)

    def test_resources_cannot_overlap_directory_or_file(self):
        self.pool.reserve(self.spec(resources=[str(self.data/'repo/src')]))
        with self.assertRaisesRegex(ValueError,'文件'): self.pool.reserve(self.spec('job-b',resources=[str(self.data/'repo/src/a.py')]))

    def test_separate_processes_obey_one_shared_pool(self):
        script='''import json,sys
from workers import Workers
try:
 Workers(sys.argv[1]).reserve(json.loads(sys.argv[2]))
 print("reserved")
except ValueError:
 print("blocked")
'''
        def launch(i):
            return subprocess.run([sys.executable,'-c',script,str(self.data),json.dumps(self.spec('process-'+str(i)))],cwd=workers.ROOT,capture_output=True,text=True,check=True).stdout.strip()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(launch,range(4)))
        self.assertEqual(results.count('reserved'),2)
        self.assertEqual(results.count('blocked'),2)

    def test_no_evidence_no_automatic_confident_choice(self):
        with self.assertRaisesRegex(ValueError,'没有证据'): self.pool.reserve(self.spec(evaluation=False))
        candidates=self.pool.candidates('coder')['candidates']
        self.assertTrue(all(not m['evidence'] for m in candidates))

    def test_evidence_exact_model_task_and_freshness(self):
        c=self.pool.config();c['evidence']=[{'id':'eval-one','model_key':'gpt-coder','model_id':c['models']['gpt-coder']['model'],'capability':'coding','benchmark':'synthetic-fixture','harness':'fixed-suite-v1','date':datetime.now(timezone.utc).date().isoformat(),'score':0.75,'source':'synthetic-unit-test','kind':'local'}]
        self.pool.save(c)
        self.pool.reserve(self.spec(evaluation=False,evidence_ids=['eval-one']))
        c['evidence'][0]['date']=(datetime.now(timezone.utc).date()-timedelta(days=91)).isoformat()
        self.pool.finish(self.pool.state()['jobs'][0]['id'],'completed','stopped')
        self.pool.save(c)
        with self.assertRaisesRegex(ValueError,'过期'): self.pool.reserve(self.spec('job-b',evaluation=False,evidence_ids=['eval-one']))
        c['evidence'][0]['model_id']='other-version'
        with self.assertRaisesRegex(ValueError,'精确'): self.pool.save(c)

    def test_custom_role_and_reject_inline_secrets(self):
        c=self.pool.config();c['roles']['test-helper']={'title':'测试助手','capability':'coding','instructions':'只提出测试样例。'};self.pool.save(c)
        self.assertEqual(self.pool.candidates('test-helper')['role'],'test-helper')
        c['providers']['kimi']['api_key']='must-not-persist'
        with self.assertRaises(ValueError):self.pool.save(c)
        self.assertNotIn('must-not-persist',self.pool.config_path.read_text())

    def test_external_only_explicit_bounded_call_and_usage(self):
        with self.external():
            job=self.pool.reserve(self.spec(model='company-kimi'))['job_id']
            response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'proposed patch'}}],'usage':{'total_tokens':24,'secret':'not stored'}}).encode())
            opener=MagicMock();opener.open.return_value=response
            with patch.object(workers,'build_opener',return_value=opener):
                with self.assertRaises(ValueError):self.pool.run(job)
                opener.open.assert_not_called()
                result=self.pool.run(job,True)
            self.assertEqual(Path(result['result_file']).read_text(),'proposed patch')
            self.assertEqual(result['usage'],{'total_tokens':24})
            request=opener.open.call_args.args[0]
            sent=json.loads(request.data)
            self.assertEqual(sent['max_tokens'],2048)
            self.assertNotIn('tools',sent)
            self.assertNotIn('synthetic-test-token',json.dumps(self.pool.state()))
            with self.assertRaises(ValueError): self.pool.run(job,True)

    def test_timeout_keeps_slot_and_no_retry_or_secret_error(self):
        with self.external():
            job=self.pool.reserve(self.spec(model='company-kimi'))['job_id']
            opener=MagicMock();opener.open.side_effect=TimeoutError('synthetic-test-token')
            with patch.object(workers,'build_opener',return_value=opener):
                with self.assertRaises(ValueError) as error:self.pool.run(job,True)
                self.assertNotIn('synthetic-test-token',str(error.exception))
                self.assertEqual(opener.open.call_count,1)
            self.assertEqual(self.pool.state()['jobs'][0]['state'],'uncertain')
            with self.assertRaises(ValueError):
                with self.pool.maintenance():pass

    def test_update_lock_blocks_workers_and_config_change(self):
        with self.pool.maintenance():
            with self.assertRaisesRegex(ValueError,'更新'):self.pool.reserve(self.spec())
            with self.assertRaises(ValueError):self.pool.save(self.pool.config())
        self.pool.reserve(self.spec())

    def test_auth_redirect_is_never_followed(self):
        with self.assertRaises(ValueError):workers.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.example')

    def test_interrupted_update_marker_requires_explicit_recovery(self):
        with self.pool.db() as db: db.execute('INSERT INTO maintenance VALUES(1,?)',('synthetic interrupted update',))
        with self.assertRaises(ValueError): self.pool.recover_maintenance()
        self.pool.recover_maintenance(True)
        self.pool.reserve(self.spec())
