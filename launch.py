"""Stable launcher: follow the installed package pointer after updates."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from updates import Updates

parser=argparse.ArgumentParser()
parser.add_argument('--data-dir',type=Path,default=Path.home()/'.sec-pro')
parser.add_argument('--port',type=int,default=8765)
args=parser.parse_args()
try:
    updater=Updates(args.data_dir)
    try:
        result=updater.auto()
        print(result.get('message',''),flush=True)
    except (OSError,ValueError) as error:
        print('Update deferred: '+str(error),file=sys.stderr)
    manifest=updater.installed()
    if 'codex_home' not in manifest: raise ValueError('Run install.py before starting the installed workspace; use start-preview.cmd for a demo.')
    package=Path(manifest['package_root'])
    sys.exit(subprocess.call([sys.executable,str(package/'secpro.py'),'serve','--port',str(args.port),'--data-dir',str(args.data_dir)]))
except (OSError,ValueError) as error:
    print(str(error),file=sys.stderr);sys.exit(2)
