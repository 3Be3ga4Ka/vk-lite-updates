"""Validate a published signed release, then atomically activate its public update/broadcast."""
import base64,hashlib,json,os,re,subprocess,tempfile,zipfile,urllib.request
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
  path=f'repos/{repo}/contents/qvk/stable.json'
  try: old=json.loads(gh('api',path))
  except subprocess.CalledProcessError: old=None
  if old:
   previous=json.loads(base64.b64decode(old['content']))
   if previous['version_code']>item['version_code']: raise ValueError('Refusing channel downgrade')
   if previous['version_code']==item['version_code']:
    if previous['sha256']!=item['sha256']: raise ValueError('Version already published with another APK')
    print('QVK update broadcast already active');return
  from distribution import publish
  item['distribution']=publish(apk,root/'mirror-parts',repo,tag)
  payload={'message':f'QVK: publish {tag} and activate update broadcast','content':base64.b64encode((json.dumps(item,ensure_ascii=False,indent=2)+'\n').encode()).decode(),'branch':'main'}
  if old: payload['sha']=old['sha']
  request=root/'commit.json';request.write_text(json.dumps(payload))
  subprocess.run(['gh','api','--method','PUT',path,'--input',str(request),'--silent'],check=True)
  try:
   with urllib.request.urlopen('https://purge.jsdelivr.net/gh/'+repo+'@main/qvk/stable.json',timeout=30) as response:
    print('CDN channel purge:',response.status)
  except Exception as error:print('CDN purge deferred:',type(error).__name__)
  print(f'QVK update broadcast active: {tag}')
if __name__=='__main__':activate(os.environ['QVK_REPOSITORY'],os.environ['QVK_RELEASE_TAG'])
