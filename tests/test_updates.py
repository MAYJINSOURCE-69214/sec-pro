import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import updates
from workers import Workers,write,read

ROOT=Path(__file__).resolve().parents[1]

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.data=self.base/'data';self.u=updates.Updates(self.data)
        self.u.save({'repository':'example/secpro','channel':'beta','auto_apply':False,'trusted':True,'interval_hours':24})

    def archive(self,unsafe=False):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('SEC-Pro-Beta/release-info.json',json.dumps({'version':'0.3.0-beta.1'}))
            z.writestr('SEC-Pro-Beta/secpro.py','print("fixture")')
            z.writestr('SEC-Pro-Beta/install.py','# fixture')
            if unsafe:z.writestr('SEC-Pro-Beta/../../escape.txt','no')
        raw=stream.getvalue()
        return raw,{'schema':1,'version':'0.3.0-beta.1','url':'https://github.com/example/secpro/releases/download/v0.3.0-beta.1/app.zip','sha256':hashlib.sha256(raw).hexdigest(),'notes':'synthetic fixture'}

    def test_version_order_and_same_version(self):
        self.assertLess(updates.version('0.2.0-beta.9'),updates.version('0.2.0'))
        self.assertLess(updates.version('0.2.0'),updates.version('0.3.0-beta.1'))
        raw,m=self.archive()
        with patch.object(updates,'fetch',return_value=json.dumps(m).encode()) as request:
            self.assertTrue(self.u.check()['available']);self.u.check(cached=True)
            self.assertEqual(request.call_count,1)

    def test_unconfigured_does_not_fetch_and_trust_required(self):
        u=updates.Updates(self.base/'unconfigured')
        with patch.object(updates,'fetch') as request:
            self.assertFalse(u.auto()['available']);request.assert_not_called()
        p=self.u.policy();p['trusted']=False;p['auto_apply']=True
        with self.assertRaises(ValueError):self.u.save(p)

    def test_stage_checksum_and_paths_verified_before_install(self):
        raw,m=self.archive()
        with patch.object(updates,'fetch',return_value=b'corrupt'),self.assertRaisesRegex(ValueError,'校验'):self.u.stage(m)
        raw,m=self.archive(unsafe=True)
        with patch.object(updates,'fetch',return_value=raw),self.assertRaisesRegex(ValueError,'越界'):self.u.stage(m)
        self.assertFalse((self.base/'escape.txt').exists())

    def test_repository_change_drops_cached_release(self):
        raw,m=self.archive()
        write(self.data/'update-state.json',{'manifest':m})
        p=self.u.policy();p['repository']='different/repository';self.u.save(p)
        self.assertEqual(self.u.state()['last_check'],{})
        with self.assertRaises(ValueError):self.u.validate_manifest(m,'different/repository')

    def test_stale_cache_never_downgrades_installed_version(self):
        write(self.data/'installation.json',{'version':'0.4.0','package_root':str(ROOT),'codex_home':'fixture','skills_home':'fixture','data_dir':str(self.data)})
        raw,m=self.archive()
        with patch.object(self.u,'check',return_value={'available':True,'manifest':m}),patch.object(self.u,'stage') as stage:
            self.assertFalse(self.u.apply(True)['available']);stage.assert_not_called()

    def test_running_workers_block_update_before_download(self):
        write(self.data/'installation.json',{'version':'0.1.0','package_root':str(ROOT),'codex_home':str(self.base/'codex'),'skills_home':str(self.base/'skills'),'data_dir':str(self.data),'gsd_installed':False})
        pool=Workers(self.data)
        pool.reserve({'task_key':'active','role':'coder','model_key':'gpt-coder','task':'fixture','reason':'synthetic evaluation fixture for update lock','evaluation':True})
        raw,m=self.archive()
        with patch.object(self.u,'check',return_value={'available':True,'manifest':m}),patch.object(self.u,'stage') as stage:
            with self.assertRaisesRegex(ValueError,'未结束'):self.u.apply(True)
            stage.assert_not_called()

    def test_real_isolated_install_update_and_rollback_preserves_personal_data(self):
        old=self.base/'old';old.mkdir()
        for name in ('install.py','secpro.py','workers.py','updates.py'):shutil.copy2(ROOT/name,old/name)
        for name in ('config','skills','agents'):shutil.copytree(ROOT/name,old/name)
        write(old/'release-info.json',{'version':'0.1.0-beta.1'})
        command=[sys.executable,str(old/'install.py'),'--codex-home',str(self.base/'codex'),'--skills-home',str(self.base/'skills'),'--data-dir',str(self.data),'--skip-gsd']
        subprocess.run(command,check=True,capture_output=True)
        personal=self.data/'private-experience.txt';personal.write_text('keep my private content')
        config=read(self.data/'workers.json');config['max_parallel']=3;write(self.data/'workers.json',config)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for path in old.rglob('*'):
                if path.is_file() and path.name!='release-info.json':z.write(path,'SEC-Pro-Beta/'+path.relative_to(old).as_posix())
            z.writestr('SEC-Pro-Beta/release-info.json',json.dumps({'version':'0.3.0-beta.1'}))
        raw=stream.getvalue();_,m=self.archive();m['sha256']=hashlib.sha256(raw).hexdigest()
        with patch.object(self.u,'check',return_value={'available':True,'manifest':m}),patch.object(updates,'fetch',return_value=raw):
            result=self.u.apply(True)
        self.assertEqual(result['version'],'0.3.0-beta.1')
        self.assertEqual(self.u.installed()['version'],'0.3.0-beta.1')
        self.assertEqual(personal.read_text(),'keep my private content')
        self.assertEqual(read(self.data/'workers.json')['max_parallel'],3)
        self.u.rollback(True)
        self.assertEqual(self.u.installed()['version'],'0.1.0-beta.1')
        self.assertEqual(read(self.data/'workers.json')['max_parallel'],3)
        self.assertIn(str(old),(self.base/'codex/AGENTS.md').read_text(encoding='utf-8'))

    def test_install_failure_uses_prior_installer(self):
        original={'version':'0.1.0','package_root':str(ROOT),'codex_home':'fixture','skills_home':'fixture','data_dir':str(self.data)}
        write(self.data/'installation.json',original)
        raw,m=self.archive()
        with patch.object(self.u,'check',return_value={'available':True,'manifest':m}),patch.object(self.u,'stage',return_value=self.base/'staged'),patch.object(self.u,'install_package',side_effect=[ValueError('fixture fail'),None]) as install:
            with self.assertRaisesRegex(ValueError,'已重新安装'):self.u.apply(True)
            self.assertEqual(install.call_count,2)
        self.assertEqual(self.u.installed(),original)
