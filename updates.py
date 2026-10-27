"""Trusted release checks, staged installation and explicit rollback."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile
from workers import Workers, read, write

ROOT = Path(__file__).resolve().parent

def version(value):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?',value)
    if not match: raise ValueError('版本须为x.y.z或x.y.z-beta.n。')
    major,minor,patch,beta = match.groups()
    return (int(major),int(minor),int(patch),1 if beta is None else 0,int(beta or 0))

def fetch(url, limit):
    with urlopen(Request(url,headers={'User-Agent':'SEC-Pro-Beta'}), timeout=30) as response:
        host = urlparse(response.geturl()).hostname or ''
        if not (host in ('raw.githubusercontent.com','github.com') or host.endswith('.githubusercontent.com')):
            raise ValueError('更新下载重定向到了非GitHub地址。')
        data = response.read(limit+1)
    if len(data)>limit: raise ValueError('更新文件超过大小限制。')
    return data

class Updates:
    def __init__(self,data):
        self.data = Path(data)
        self.data.mkdir(parents=True,exist_ok=True)
        self.settings = self.data/'updates.json'

    def policy(self):
        return read(self.settings) if self.settings.exists() else {'repository':'','channel':'beta','auto_apply':False,'trusted':False,'interval_hours':24}

    def save(self,value):
        if set(value) != {'repository','channel','auto_apply','trusted','interval_hours'}: raise ValueError('更新配置字段不完整。')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value['repository']): raise ValueError('填写维护者仓库owner/repo。')
        if value['channel'] not in ('stable','beta') or any(type(value[k]) is not bool for k in ('trusted','auto_apply')) or type(value['interval_hours']) is not int or not 1<=value['interval_hours']<=168:
            raise ValueError('请选择stable/beta、明确信任/自动更新及1至168小时检查间隔。')
        if value['auto_apply'] and not value['trusted']: raise ValueError('自动更新只接受明确信任的维护者仓库。')
        write(self.settings,value)
        # A changed trust target must never reuse a stale cached manifest.
        write(self.data/'update-state.json',{})
        return {'message':'已保存更新策略。只有明确启用自动更新后，任务入口才会安装可信仓库的新版本。'}

    def installed(self):
        path = self.data/'installation.json'
        return read(path) if path.exists() else {'version':read(ROOT/'release-info.json')['version'],'package_root':str(ROOT)}

    def state(self):
        cache = self.data/'update-state.json'
        return {'policy':self.policy(),'installed':self.installed()['version'],'running':read(ROOT/'release-info.json')['version'], 'last_check':read(cache) if cache.exists() else {}}

    def check(self,cached=False):
        p = self.policy()
        if not p['repository']: return {'message':'尚未发布并配置维护者仓库；没有远程版本可检查。','available':False}
        state = self.state()['last_check']
        if cached and state.get('repository')==p['repository'] and state.get('channel')==p['channel'] and time.time()-state.get('checked_at',0)<p['interval_hours']*3600:
            return state
        repo = p['repository']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or p['channel'] not in ('stable','beta'): raise ValueError('更新源配置无效。')
        manifest = json.loads(fetch(f'https://raw.githubusercontent.com/{repo}/main/releases/{p["channel"]}.json',65536))
        self.validate_manifest(manifest,repo)
        installed = self.installed()['version']
        available = version(manifest['version'])>version(installed)
        value = {'checked_at':time.time(),'repository':repo,'channel':p['channel'],'installed':installed,'available':available,'manifest':manifest,'message':'发现新版本，可下载并安装。' if available else '当前版本没有可用升级。'}
        write(self.data/'update-state.json',value)
        return value

    @staticmethod
    def validate_manifest(m,repo):
        if not isinstance(m,dict) or set(m) != {'schema','version','url','sha256','notes'} or m['schema']!=1: raise ValueError('不支持的发行清单。')
        version(m['version'])
        if not re.fullmatch(r'[a-f0-9]{64}',m['sha256']): raise ValueError('缺少SHA-256校验。')
        url = urlparse(m['url'])
        if url.scheme!='https' or url.netloc!='github.com' or url.query or url.fragment or not url.path.startswith('/'+repo+'/releases/download/') or not url.path.endswith('.zip'):
            raise ValueError('发行包必须来自配置的维护者GitHub仓库。')

    def stage(self,m):
        self.validate_manifest(m,self.policy()['repository'])
        raw = fetch(m['url'],40*1024*1024)
        if hashlib.sha256(raw).hexdigest()!=m['sha256']: raise ValueError('发行包校验失败，未安装。')
        destination = self.data/'releases'/m['version']
        if destination.exists():
            receipt = destination/'stage.json'
            if not receipt.exists() or read(receipt).get('sha256')!=m['sha256']: raise ValueError('同版本存在不同内容，拒绝覆盖。')
            return destination/'SEC-Pro-Beta'
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='secpro-stage-',dir=destination.parent) as folder:
            folder = Path(folder)
            archive = folder/'release.zip'; archive.write_bytes(raw)
            with zipfile.ZipFile(archive) as z:
                entries = z.infolist()
                if len(entries)>3000 or sum(v.file_size for v in entries)>100*1024*1024: raise ValueError('解压体积超限。')
                names=set()
                for entry in entries:
                    name=PurePosixPath(entry.filename)
                    if (not name.parts or name.parts[0]!='SEC-Pro-Beta' or '..' in name.parts or '\\' in entry.filename or ':' in entry.filename or name.is_absolute() or (entry.external_attr>>16)&0o170000==0o120000 or entry.filename.casefold() in names): raise ValueError('拒绝越界、链接或重复的更新文件。')
                    names.add(entry.filename.casefold())
                z.extractall(folder)
            package=folder/'SEC-Pro-Beta'
            if read(package/'release-info.json')['version']!=m['version'] or not (package/'install.py').is_file() or not (package/'secpro.py').is_file(): raise ValueError('包内版本或安装入口不匹配。')
            # Data is outside releases; a release must not carry employee state.
            if any((package/p).exists() for p in ('.local-preview','personal-data','preview-data','.env','settings.json')): raise ValueError('发行包包含运行数据。')
            write(folder/'stage.json',{'sha256':m['sha256']})
            destination.mkdir()
            shutil.move(str(package),str(destination/'SEC-Pro-Beta'))
            shutil.copy2(folder/'stage.json',destination/'stage.json')
        return destination/'SEC-Pro-Beta'

    def install_package(self,package,installation):
        # A changed upstream GSD needs a separate full install, not an unsafe
        # partial downgrade of its global files during a background update.
        old = Path(installation['package_root'])
        if installation.get('gsd_installed') and (package/'vendor/gsd-lock.json').read_bytes()!=(old/'vendor/gsd-lock.json').read_bytes():
            raise ValueError('该版本同时升级GSD：请在空闲时让Codex执行新版README完整安装，自动更新没有替换全局GSD。')
        args=[sys.executable,str(package/'install.py'),'--codex-home',installation['codex_home'],'--skills-home',installation['skills_home'],'--data-dir',str(self.data),'--skip-gsd']
        result = subprocess.run(args,capture_output=True,text=True,encoding='utf-8',timeout=90)
        if result.returncode: raise ValueError('新版安装器失败；查看本机备份和更新记录，不宣称更新成功。')
        current=read(self.data/'installation.json')
        current['gsd_installed']=installation.get('gsd_installed',False)
        current['gsd_override_conflicts']=installation.get('gsd_override_conflicts',[])
        write(self.data/'installation.json',current)

    def apply(self,confirmed=False,automatic=False):
        p=self.policy()
        if not p['trusted'] or not (confirmed or (automatic and p['auto_apply'])): raise ValueError('请先信任维护者仓库，并确认安装或启用自动更新。')
        installation=self.installed()
        if not all(k in installation for k in ('codex_home','skills_home','data_dir')): raise ValueError('当前只是预览，先安装后才可以更新员工端。')
        check=self.check(cached=True)
        if not check.get('available'): return check
        if version(check['manifest']['version']) <= version(installation['version']):
            return {'available':False,'message':'缓存版本不高于当前安装，未执行降级。'}
        with Workers(self.data).maintenance():
            package=self.stage(check['manifest'])
            write(self.data/'previous-installation.json',installation)
            try:
                self.install_package(package,installation)
            except Exception:
                try:
                    self.install_package(Path(installation['package_root']),installation)
                    write(self.data/'installation.json',installation)
                except Exception:
                    raise ValueError('更新失败且自动恢复未完成；停止继续更新，请依据previous-installation.json和文件备份人工恢复。') from None
                raise ValueError('更新未完成，已重新安装先前SEC版本；个人数据和配置保留。') from None
        write(self.data/'update-state.json',{})
        return {'message':'新版已安装；个人经验、API配置和模型选择保留。请重启工作台，并在Codex新会话使用新版入口。','version':check['manifest']['version']}

    def rollback(self,confirmed=False):
        if not confirmed: raise ValueError('回退需明确确认。')
        previous=read(self.data/'previous-installation.json')
        with Workers(self.data).maintenance():
            self.install_package(Path(previous['package_root']),self.installed())
            write(self.data/'installation.json',previous)
        write(self.data/'update-state.json',{})
        return {'message':'已恢复上一个安装版本，个人数据未回滚。请重启工作台和Codex会话。','version':previous['version']}

    def auto(self):
        check=self.check(cached=True)
        if check.get('available') and self.policy()['auto_apply']: return self.apply(automatic=True)
        return check
