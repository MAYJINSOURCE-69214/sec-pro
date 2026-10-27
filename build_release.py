"""Build only local artifacts. This script never publishes or calls GitHub."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parent

def build(repository=None):
    version=json.loads((ROOT/'release-info.json').read_text())['version']
    files=[ROOT/p for p in ('README.md','LICENSE','secpro.py','workers.py','updates.py','release-info.json','build_release.py','install.py','install.ps1','install.sh','start-preview.cmd','start.cmd','launch.py','THIRD_PARTY_NOTICES.md','.gitignore')]
    for folder in ('web','skills','agents','config','tests','library','demo','vendor'):
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    target=ROOT/'dist'/('SEC-Pro-Beta-'+version+'.zip'); target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files): z.write(p,'SEC-Pro-Beta/'+p.relative_to(ROOT).as_posix())
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    result={'archive':str(target),'sha256':digest,'files':len(files)}
    if repository:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository): raise ValueError('Use owner/repo')
        manifest={'schema':1,'version':version,'url':f'https://github.com/{repository}/releases/download/v{version}/{target.name}','sha256':digest,'notes':'维护者请在发布前填写已验证的更新内容。'}
        path=ROOT/'dist'/('beta.json' if '-beta.' in version else 'stable.json')
        path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');result['manifest']=str(path)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repository');args=parser.parse_args()
    print(json.dumps(build(args.repository),ensure_ascii=False))
