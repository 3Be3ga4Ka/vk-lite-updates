"""Validate a published signed release, then atomically activate its public update/broadcast."""
import base64,hashlib,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path

def gh(*args):
 return subprocess.check_output(['gh',*args],text=True)
def activate(repo,tag):
 if not re.fullmatch(r'qvk-public[0-9]+',tag): raise ValueError('Not a QVK public tag')
 release=json.loads(gh('api',f'repos/{repo}/releases/tags/{tag}'))
 if release['draft'] or release['prerelease']: raise ValueError('Stable published release required')
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)
  subprocess.run(['gh','release','download',tag,'--repo',repo,'--pattern','qvk-update.json','--dir',td],check=True)
  item=json.loads((root/'qvk-update.json').read_text())
  name=item['apk_url'].rsplit('/',1)[-1]
  if item['package']!='ru.qmods.qvk' or item['schema']!=1 or not re.fullmatch(r'QVK_[A-Za-z0-9_.-]+\.apk',name): raise ValueError('Wrong application')
  if item['apk_url']!=f'https://github.com/{repo}/releases/download/{tag}/{name}': raise ValueError('Wrong APK URL')
  if not isinstance(item['version_code'],int) or not 0<item['version_code']<2147483648: raise ValueError('Wrong version')
  if not isinstance(item['apk_size'],int) or not 0<item['apk_size']<=536870912: raise ValueError('Wrong APK size')
  if not re.fullmatch('[a-f0-9]{64}',item['sha256']) or len(item.get('text',''))>4000: raise ValueError('Invalid metadata')
  subprocess.run(['gh','release','download',tag,'--repo',repo,'--pattern',name,'--dir',td],check=True)
  apk=root/name
  if apk.stat().st_size!=item['apk_size'] or hashlib.sha256(apk.read_bytes()).hexdigest()!=item['sha256']: raise ValueError('APK checksum mismatch')
  with zipfile.ZipFile(apk) as z:
   if z.testzip(): raise ValueError('Invalid APK ZIP')
  sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
  signers=sorted((sdk/'build-tools').glob('*/apksigner'))
  if not signers: raise RuntimeError('Android build tools unavailable')
  output=subprocess.check_output([str(signers[-1]),'verify','--verbose','--print-certs',str(apk)],text=True)
  expected='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
  if set(re.findall(r'certificate sha-256 digest:\s*([0-9a-fA-F]{64})', output.lower())) != {expected}: raise ValueError('Wrong QVK signer: ' + repr(re.findall(r'certificate[^\n]*', output)))
  aapt=signers[-1].parent/'aapt'
  badging=subprocess.check_output([str(aapt),'dump','badging',str(apk)],text=True).splitlines()[0]
  if f"name='ru.qmods.qvk'" not in badging or f"versionCode='{item['version_code']}'" not in badging or f"versionName='{item['version_name']}'" not in badging: raise ValueError('APK identity mismatch')
  # Publish small immutable parts so two independent CDNs can also serve the full signed APK.
  mirror=root/'mirror-repo'
  subprocess.run(['gh','repo','clone',repo,str(mirror),'--','--depth','1','--filter=blob:none','--sparse'],check=True)
  subprocess.run(['git','sparse-checkout','set','qvk/distribution'],cwd=mirror,check=True)
  directory=mirror/'qvk/distribution';directory.mkdir(parents=True,exist_ok=True)
  for previous_part in directory.glob('apk.part*'):previous_part.unlink()
  parts=[]
  with apk.open('rb') as stream:
   while chunk:=stream.read(8*1024*1024):
    part_name=f'apk.part{len(parts):03}';(directory/part_name).write_bytes(chunk);parts.append(dict(name=part_name,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest()))
  subprocess.run(['git','add','qvk/distribution'],cwd=mirror,check=True)
  subprocess.run(['git','-c','user.name=QVK release automation','-c','user.email=qvk-release@users.noreply.github.com','commit','--allow-empty','-m',f'Mirror signed {tag} APK for CDN delivery'],cwd=mirror,check=True)
  subprocess.run(['git','pull','--rebase','origin','main'],cwd=mirror,check=True)
  subprocess.run(['git','-c','credential.helper=!gh auth git-credential','push','origin','HEAD:main'],cwd=mirror,check=True)
  commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=mirror,text=True).strip()
  item['distribution']={'commit':commit,'parts':parts}
  path=f'repos/{repo}/contents/qvk/stable.json'
  try: old=json.loads(gh('api',path))
  except subprocess.CalledProcessError: old=None
  if old:
   previous=json.loads(base64.b64decode(old['content']))
   if previous['version_code']>item['version_code']: raise ValueError('Refusing channel downgrade')
   if previous['version_code']==item['version_code']:
    if previous['sha256']!=item['sha256']: raise ValueError('Version already published with another APK')
    print('QVK update broadcast already active');return
  payload={'message':f'QVK: publish {tag} and activate update broadcast','content':base64.b64encode((json.dumps(item,ensure_ascii=False,indent=2)+'\n').encode()).decode(),'branch':'main'}
  if old: payload['sha']=old['sha']
  request=root/'commit.json';request.write_text(json.dumps(payload))
  subprocess.run(['gh','api','--method','PUT',path,'--input',str(request),'--silent'],check=True)
  print(f'QVK update broadcast active: {tag}')
if __name__=='__main__':activate(os.environ['QVK_REPOSITORY'],os.environ['QVK_RELEASE_TAG'])
