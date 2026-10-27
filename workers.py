"""Provider-neutral bounded workers. No second project planner and no recursive agents."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)

def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}', value):
        raise ValueError('标识使用2至64位小写字母、数字和连字符。')
    return value

def https_url(value):
    p = urlparse(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('接口必须是无用户名、密码或查询参数的 HTTPS 地址。')
    return value.rstrip('/')

def validate(config):
    if set(config) - {'schema','max_parallel','providers','models','roles','evidence'} or config.get('schema') != 1:
        raise ValueError('不支持的分工配置。不要将密钥写入配置。')
    if type(config.get('max_parallel')) is not int or not 1 <= config['max_parallel'] <= 8:
        raise ValueError('并发上限须为1至8。')
    providers, models, roles = (config.get(k, {}) for k in ('providers','models','roles'))
    if not all(isinstance(v, dict) for v in (providers,models,roles)) or not models or not roles:
        raise ValueError('需要供应商、模型与角色字典。')
    for key, p in providers.items():
        ident(key)
        if set(p) - {'kind','enabled','base_url','key_env'} or p.get('kind') not in ('codex','chat-completions') or type(p.get('enabled')) is not bool:
            raise ValueError('供应商只接受类型、启用状态、地址与密钥环境变量名。')
        if p['kind'] == 'chat-completions':
            https_url(p.get('base_url',''))
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,80}', p.get('key_env','')):
                raise ValueError('填写密钥的环境变量名，不填写密钥本身。')
    for key, m in models.items():
        ident(key)
        if set(m) - {'provider','model','effort','capabilities','max_output_tokens','parameters','price'}:
            raise ValueError('模型配置含未知字段。')
        if m.get('provider') not in providers or not isinstance(m.get('model'), str) or len(m['model']) > 160:
            raise ValueError('模型须引用已配置供应商和实际模型ID。')
        if providers[m['provider']]['enabled'] and not m['model'].strip():
            raise ValueError('启用前请填实际模型ID。')
        if m.get('effort') not in ('low','medium','high') or not isinstance(m.get('capabilities'), list):
            raise ValueError('需明确思考强度和能力列表。')
        for cap in m['capabilities']: ident(cap)
        if type(m.get('max_output_tokens')) is not int or not 128 <= m['max_output_tokens'] <= 16000:
            raise ValueError('每次输出上限128至16000。')
        if set(m.get('parameters', {})) - {'temperature','top_p','reasoning_effort','enable_thinking'}:
            raise ValueError('不允许覆盖模型、消息、鉴权或工具字段。')
        price = m.get('price')
        if price is not None and (set(price) != {'currency','input_per_million','output_per_million'} or price['currency'] not in ('USD','CNY') or any(type(price[k]) not in (int,float) or not 0 <= price[k] < 100000 for k in ('input_per_million','output_per_million'))):
            raise ValueError('价格须标币种及每百万输入/输出token价格；未知填null。')
    for key, role in roles.items():
        ident(key)
        if set(role) != {'title','capability','instructions'} or not all(isinstance(v,str) and v for v in role.values()):
            raise ValueError('自定义角色需要title、capability和instructions。')
        ident(role['capability'])
    ids = set()
    for e in config.get('evidence', []):
        required = {'id','model_key','model_id','capability','benchmark','harness','date','score','source','kind'}
        if set(e) != required or e['id'] in ids or e['model_key'] not in models:
            raise ValueError('评测证据字段不完整、重复或模型不存在。')
        ident(e['id']); ids.add(e['id'])
        if e['model_id'] != models[e['model_key']]['model'] or e['kind'] not in ('published','local'):
            raise ValueError('跑分须绑定精确模型版本与来源类型。')
        if type(e['score']) not in (int,float) or not 0 <= e['score'] <= 1:
            raise ValueError('分数须归一化为0至1，越高越好。')
        if not all(isinstance(e[k],str) and e[k].strip() for k in ('benchmark','harness','source')):
            raise ValueError('跑分必须有测试名、运行条件和证据出处。')
        datetime.fromisoformat(e['date']).date()
    return config

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('拒绝把带凭据的模型请求重定向到其他地址。')

class Workers:
    def __init__(self, data):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data / 'workers.json'
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, task_key TEXT UNIQUE, state TEXT, payload TEXT); CREATE TABLE IF NOT EXISTS maintenance(id INTEGER PRIMARY KEY CHECK(id=1), reason TEXT);')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.data / 'workers.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def config(self):
        return validate(read(self.config_path if self.config_path.exists() else ROOT / 'config/workers.json'))

    def save(self, config):
        validate(config)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('reserved','running','uncertain')").fetchone() or db.execute('SELECT 1 FROM maintenance').fetchone():
                raise ValueError('尚有工人在运行或更新中，先结束后再修改配置。')
            if self.config_path.exists(): write(self.data / 'backups' / ('workers-' + uuid.uuid4().hex + '.json'), read(self.config_path))
            write(self.config_path, config)
        return {'message':'已保存供应商与角色配置；未调用任何模型。'}

    def candidates(self, role):
        c = self.config()
        if role not in c['roles']: raise ValueError('未知角色。')
        cap = c['roles'][role]['capability']
        result = []
        today = datetime.now(timezone.utc).date()
        for key, m in c['models'].items():
            if cap not in m['capabilities']: continue
            p = c['providers'][m['provider']]
            evidence = [e for e in c['evidence'] if e['model_key'] == key and e['capability'] == cap and 0 <= (today - datetime.fromisoformat(e['date']).date()).days <= 90]
            ready = p['enabled'] and (p['kind'] == 'codex' or bool(os.environ.get(p['key_env'])))
            result.append({'model_key':key, 'model':m['model'], 'provider':m['provider'], 'configured':ready,
                           'availability':'原生模型权限须由当前Codex核实' if p['kind']=='codex' else ('已找到密钥变量，接口未实测' if ready else '未启用或缺少密钥变量'),
                           'price':m.get('price'), 'evidence':evidence, 'assessment':'有近期证据，需核对任务与测试条件' if evidence else '缺少近期证据，不猜跑分'})
        return {'role':role,'candidates':result,'decision_rule':'主模型先核对实际任务与可用性；只比较同benchmark/harness/任务的精确模型版本，本地结果与公开分数分别看。质量达标后比较同币种价格和延迟。无证据仅允许明确标记的小规模试评，不自动选最贵模型。'}

    def state(self):
        with self.db() as db:
            rows = [json.loads(r['payload']) | {'state':r['state']} for r in db.execute('SELECT * FROM jobs ORDER BY rowid DESC LIMIT 20')]
        return {'config':self.config(), 'jobs':[{k:r.get(k) for k in ('id','role','model_key','task_key','state','reason','usage','result_file')} for r in rows]}

    def reserve(self, spec):
        c = self.config()
        role, key = spec.get('role'), spec.get('model_key')
        if role not in c['roles'] or key not in c['models']: raise ValueError('选择已配置的角色和模型。')
        m, r = c['models'][key], c['roles'][role]
        p = c['providers'][m['provider']]
        if not p['enabled'] or r['capability'] not in m['capabilities']: raise ValueError('供应商未启用或能力不匹配。')
        if p['kind'] != 'codex' and not os.environ.get(p['key_env']): raise ValueError('缺少公司提供的密钥环境变量；不自动改用别的模型。')
        if not isinstance(spec.get('task'),str) or not 1 <= len(spec['task']) <= 32000: raise ValueError('任务正文1至32000字符，仅传已批准给该供应商的内容。')
        if not isinstance(spec.get('task_key'),str) or not 1 <= len(spec['task_key']) <= 160: raise ValueError('需要项目内唯一工单编号。')
        if not isinstance(spec.get('reason'),str) or not 10 <= len(spec['reason']) <= 2000: raise ValueError('主模型需写明选择理由、成本和验证方式。')
        valid_evidence = {e['id'] for v in self.candidates(role)['candidates'] if v['model_key']==key for e in v['evidence']}
        selected = spec.get('evidence_ids', [])
        if not isinstance(selected,list) or set(selected) - valid_evidence: raise ValueError('选择的证据过期、模型不符或不适用。')
        if not selected and spec.get('evaluation') is not True: raise ValueError('没有证据时只能明确选择小规模试评，不能冒充有据的正式路由。')
        resources = spec.get('resources', [])
        if not isinstance(resources,list) or len(resources)>30 or any(not isinstance(v,str) or not v for v in resources): raise ValueError('文件归属须为路径列表。')
        resources = sorted(set(os.path.normcase(str(Path(v).resolve())) for v in resources))
        payload = {'id':uuid.uuid4().hex, 'task_key':spec['task_key'], 'task':spec['task'], 'role':role,'model_key':key,'model':m,'provider':p,'instructions':r['instructions'], 'reason':spec['reason'],'evidence_ids':selected,'evaluation':spec.get('evaluation') is True,'resources':resources,'created_at':time.time()}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM maintenance').fetchone(): raise ValueError('系统更新期间暂停接收新工单。')
            old = db.execute('SELECT * FROM jobs WHERE task_key=?',(payload['task_key'],)).fetchone()
            if old: raise ValueError('该工单已存在，先查询结果，不重复派活。')
            active = [json.loads(row['payload']) for row in db.execute("SELECT payload FROM jobs WHERE state IN ('reserved','running','uncertain')")]
            if len(active) >= c['max_parallel']: raise ValueError('GPT与第三方工人共用的并发名额已满。')
            for prior in active:
                for a in resources:
                    for b in prior['resources']:
                        if a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep): raise ValueError('该文件或目录已有工人负责，不能重复写入。')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(payload['id'],payload['task_key'],'reserved',json.dumps(payload,ensure_ascii=False)))
        result = {'job_id':payload['id'],'kind':p['kind'],'model_key':key}
        if p['kind']=='codex':
            result['request'] = {'task_name':'sec_'+role+'_'+payload['id'][:8], 'model':m['model'], 'reasoning_effort':m['effort'], 'fork_turns':'none', 'message':r['instructions']+'\n只处理本工单，不递归委派。完成后报告产物与证据。\n'+spec['task']}
        else: result['next'] = 'worker-run --job '+payload['id']+' --allow-api；会向配置的公司供应商发送本工单正文。'
        return result

    def finish(self, job, state, note, usage=None, result_file=None):
        if state not in ('completed','failed','uncertain','cancelled'): raise ValueError('无效结束状态。')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
            if not row: raise ValueError('未知工单。')
            value = json.loads(row['payload'])
            value.update(note=str(note)[:2000], usage=usage, result_file=result_file)
            db.execute('UPDATE jobs SET state=?,payload=? WHERE id=?',(state,json.dumps(value,ensure_ascii=False),job))
        return {'job_id':job,'state':state}

    def run(self, job, allow_api=False):
        if not allow_api: raise ValueError('调用第三方需明确 --allow-api，确认本工单可以发送给配置的供应商。')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
            if not row or row['state'] != 'reserved': raise ValueError('仅执行尚未开始的工单，失败或超时不自动重试。')
            v = json.loads(row['payload']); p,m = v['provider'],v['model']
            if p['kind'] != 'chat-completions': raise ValueError('原生Codex工单请用委派工具运行，再登记结果。')
            key = os.environ.get(p['key_env'])
            if not key: raise ValueError('密钥变量不可用。')
            db.execute('UPDATE jobs SET state=? WHERE id=?',('running',job))
        body = {'model':m['model'],'messages':[{'role':'system','content':v['instructions']+'\n只返回本任务产物。你没有本机工具；不得声称执行测试，不递归委派。'},{'role':'user','content':v['task']}], 'max_tokens':min(m['max_output_tokens'],2048) if v['evaluation'] else m['max_output_tokens'], **m.get('parameters',{})}
        try:
            req = Request(https_url(p['base_url'])+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
            with build_opener(NoRedirect()).open(req,timeout=90) as response:
                raw = response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024: raise ValueError('响应超过上限。')
            value = json.loads(raw)
            content = value['choices'][0]['message']['content']
            if not isinstance(content,str) or not content.strip(): raise ValueError('未返回可审核的文本产物。')
            target = self.data / 'runs' / job / 'result.txt'
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(content,encoding='utf-8')
            usage = {k:v for k,v in value.get('usage',{}).items() if k in ('prompt_tokens','completion_tokens','total_tokens') and type(v) is int}
            self.finish(job,'completed','供应商返回产物，仍需主模型审核与本地测试。',usage,str(target))
            return {'job_id':job,'result_file':str(target),'usage':usage,'message':'产物已保存，未自动执行或应用其代码。'}
        except Exception:
            self.finish(job,'uncertain','请求结果未确认；为避免重复计费保留占位。核查供应商和本地状态后再明确结束工单。')
            raise ValueError('模型请求未完成；不显示可能含敏感内容的供应商响应，不自动重试或升级。') from None

    @contextmanager
    def maintenance(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('reserved','running','uncertain')").fetchone() or db.execute('SELECT 1 FROM maintenance').fetchone():
                raise ValueError('有未结束工单或更新正在运行，不能切换版本。')
            db.execute('INSERT INTO maintenance VALUES(1,?)',('release-update',))
        try: yield
        finally:
            with self.db() as db: db.execute('DELETE FROM maintenance WHERE id=1')

    def recover_maintenance(self,confirmed=False):
        if not confirmed: raise ValueError('先确认更新进程已经结束，再清除中断遗留标记。')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('reserved','running','uncertain')").fetchone(): raise ValueError('仍有未结束工单，不能恢复更新锁。')
            db.execute('DELETE FROM maintenance WHERE id=1')
        return {'message':'已清除更新中断标记；这不会终止进程或证明安装完整。请核对当前版本，必要时执行回退。'}
