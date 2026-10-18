#!/usr/bin/env python3
"""One-command signed APK publication through GitHub Actions, including update broadcast."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,tempfile,os
REPO='3Be3ga4Ka/vk-lite-updates'
def run(*args,**kw):return subprocess.run(list(map(str,args)),check=True,**kw)
def main():
 p=argparse.ArgumentParser();p.add_argument('apk',type=Path);p.add_argument('--notes',type=Path,required=True);p.add_argument('--public',type=int,required=True);args=p.parse_args();apk=args.apk.resolve();notes=args.notes.resolve()
 if not re.fullmatch(r'QVK_[A-Za-z0-9_.-]+\.apk',apk.name) or not 0<apk.stat().st_size<=536870912:raise ValueError('Invalid QVK APK')
 aapt=shutil.which('aapt')
 if not aapt:
  candidates=list(Path(os.environ.get('ANDROID_HOME','/usr/local/lib/android/sdk')).glob('build-tools/*/aapt'))+[Path('/workspace/sova-fix/tools/sdk/android-15/aapt')]
  aapt=next((str(x) for x in reversed(candidates) if x.is_file()),None)
 if not aapt:raise RuntimeError('Install Android SDK build-tools (aapt)')
 badging=subprocess.check_output([aapt,'dump','badging',str(apk)],text=True).splitlines()[0]
 m=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
 if not m or m[1]!='ru.qmods.qvk':raise ValueError('Not a QVK package')
 tag=f'qvk-public{args.public}';branch=f'qvk-upload-public{args.public}';text=notes.read_text()
 if len(text)>4000:raise ValueError('Release notes exceed 4000 characters')
 item=dict(schema=1,package=m[1],version_code=int(m[2]),version_name=m[3],apk_size=apk.stat().st_size,sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),apk_url=f'https://github.com/{REPO}/releases/download/{tag}/{apk.name}',text=text)
 existing=subprocess.run(['gh','release','view',tag,'--repo',REPO,'--json','isDraft'],capture_output=True,text=True)
 if existing.returncode==0:
  if not json.loads(existing.stdout)['isDraft']:raise ValueError('Release already published; refusing replacement')
 else:run('gh','release','create',tag,'--repo',REPO,'--draft','--latest=false','--title',f'QVK public{args.public} · {m[3]}','--notes-file',notes)
 releases=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/releases?per_page=100'],text=True))
 release_id=next(x['id'] for x in releases if x['tag_name']==tag and x['draft'])
 with tempfile.TemporaryDirectory(prefix='qvk-publish-') as td:
  repo=Path(td)/'repo';run('gh','repo','clone',REPO,repo,'--','--depth','1');run('git','switch','-c',branch,cwd=repo)
  root=repo/'qvk/staging';root.mkdir(parents=True,exist_ok=True);parts=[]
  def push_parts(message):
   run('git','add','qvk',cwd=repo)
   run('git','-c','user.name=QVK release automation','-c','user.email=qvk-release@users.noreply.github.com','commit','-m',message,cwd=repo)
   run('git','-c','credential.helper=!gh auth git-credential','-c','core.compression=0','-c','pack.window=0','-c','http.postBuffer=524288000','push','origin',f'HEAD:{branch}',cwd=repo)
  with apk.open('rb') as stream:
   while chunk:=stream.read(32*1024*1024):
    name=f'apk.part{len(parts):03}';(root/name).write_bytes(chunk);parts.append(dict(name=name,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
    push_parts(f'Stage {tag} part {len(parts)}')
  run('git','mv','qvk/staging','qvk/incoming',cwd=repo)
  root=repo/'qvk/incoming'
  (root/'manifest.json').write_text(json.dumps(dict(tag=tag,release_id=release_id,update=item,chunks=parts),ensure_ascii=False,indent=2)+'\n')
  push_parts(f'Stage verified {tag} for automatic publication')
 print(f'https://github.com/{REPO}/actions/workflows/qvk-upload.yml')
if __name__=='__main__':main()
