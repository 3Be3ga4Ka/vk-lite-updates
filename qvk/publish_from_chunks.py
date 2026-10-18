"""GitHub runner upload path when an external CLI identity cannot use uploads.github.com."""
import hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
from publish_channel import activate,gh

def main():
 repo=os.environ['QVK_REPOSITORY'];ref=os.environ['QVK_STAGING_REF']
 if repo!='3Be3ga4Ka/vk-lite-updates' or not re.fullmatch(r'qvk-upload-public[0-9]+',ref):raise ValueError('Wrong release staging branch')
 root=Path('qvk/incoming');data=json.loads((root/'manifest.json').read_text());item=data['update'];tag=data['tag'];name=item['apk_url'].rsplit('/',1)[-1]
 if tag!=ref.replace('qvk-upload-','qvk-') or not re.fullmatch(r'QVK_[A-Za-z0-9_.-]+\.apk',name):raise ValueError('Wrong release tag or filename')
 if item['package']!='ru.qmods.qvk' or item['apk_url']!=f'https://github.com/{repo}/releases/download/{tag}/{name}':raise ValueError('Wrong QVK channel')
 if not 0<item['apk_size']<=536870912 or not 0<len(data['chunks'])<=16:raise ValueError('Release size limit')
 with tempfile.TemporaryDirectory() as td:
  apk=Path(td)/name;digest=hashlib.sha256();size=0
  with apk.open('wb') as out:
   for n,entry in enumerate(data['chunks']):
    if entry['name']!=f'apk.part{n:03}' or not 0<entry['bytes']<=40*1024*1024:raise ValueError('Chunk metadata')
    chunk=(root/entry['name']).read_bytes()
    if len(chunk)!=entry['bytes'] or hashlib.sha256(chunk).hexdigest()!=entry['sha256']:raise ValueError('Chunk checksum mismatch')
    out.write(chunk);digest.update(chunk);size+=len(chunk)
  if size!=item['apk_size'] or digest.hexdigest()!=item['sha256']:raise ValueError('APK checksum mismatch')
  sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
  signer=sorted((sdk/'build-tools').glob('*/apksigner'))[-1]
  verified=subprocess.check_output([str(signer),'verify','--verbose','--print-certs',str(apk)],text=True)
  cert='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
  if f'Signer #1 certificate SHA-256 digest: {cert}' not in verified:raise ValueError('Wrong signer')
  metadata=subprocess.check_output([str(signer.parent/'aapt'),'dump','badging',str(apk)],text=True).splitlines()[0]
  for attribute,value in [('name','ru.qmods.qvk'),('versionCode',str(item['version_code'])),('versionName',item['version_name'])]:
   if f"{attribute}='{value}'" not in metadata:raise ValueError('APK metadata mismatch')
  manifest=Path(td)/'qvk-update.json';manifest.write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n')
  release=json.loads(gh('api',f'repos/{repo}/releases/tags/{tag}'))
  if release['draft']:
   subprocess.run(['gh','release','upload',tag,str(apk),str(manifest),'--repo',repo,'--clobber'],check=True)
   subprocess.run(['gh','release','edit',tag,'--repo',repo,'--draft=false','--latest=false'],check=True)
  # GITHUB_TOKEN release events do not start another workflow; activate explicitly here.
  activate(repo,tag)
  subprocess.run(['gh','api','--method','DELETE',f'repos/{repo}/git/refs/heads/{ref}','--silent'],check=True)
  print('Published, broadcast activated, temporary upload branch removed')
if __name__=='__main__':main()
